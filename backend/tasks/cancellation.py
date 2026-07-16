"""
Cooperative task cancellation for Celery workers running under -P threads or -P solo.

Since threads cannot be killed via SIGKILL, we use a Redis-based stop flag.
Each task calls check_cancelled(task_id) at every checkpoint — if a stop flag
is found, TaskCancelled is raised and the task cleans up gracefully.

Usage in a task:
    from tasks.cancellation import check_cancelled, set_stop_flag, clear_stop_flag

Stop from outside (e.g. the stop endpoint):
    set_stop_flag(task_id)          # signals the task to abort
    clear_stop_flag(task_id)        # cleanup (called automatically on task end)
"""

import logging
from qa_engine.redis_client import get_redis_client

logger = logging.getLogger(__name__)

STOP_FLAG_TTL = 3600  # seconds — auto-expires so Redis stays clean


class TaskCancelled(Exception):
    """Raised inside a task when a stop flag is detected."""
    pass


def set_stop_flag(task_id: str) -> None:
    """Set the stop flag for a task. Called by the stop endpoint."""
    try:
        r = get_redis_client()
        r.setex(f"stop_flag:{task_id}", STOP_FLAG_TTL, "1")
        logger.info(f"[CANCELLATION] Stop flag set for task {task_id}")
    except Exception as e:
        logger.error(f"[CANCELLATION] Failed to set stop flag for {task_id}: {e}")


def clear_stop_flag(task_id: str) -> None:
    """Remove the stop flag. Called when a task ends (success, failure, or cancel)."""
    try:
        r = get_redis_client()
        r.delete(f"stop_flag:{task_id}")
    except Exception as e:
        logger.warning(f"[CANCELLATION] Failed to clear stop flag for {task_id}: {e}")


def is_cancelled(task_id: str) -> bool:
    """Returns True if a stop flag has been set for this task."""
    try:
        r = get_redis_client()
        return r.exists(f"stop_flag:{task_id}") == 1
    except Exception as e:
        logger.warning(f"[CANCELLATION] Redis check failed for {task_id}: {e}")
        return False


def check_cancelled(task_id: str) -> None:
    """
    Raise TaskCancelled if this task has been asked to stop.
    Call this at every major checkpoint inside a task.
    """
    if is_cancelled(task_id):
        logger.info(f"[CANCELLATION] Task {task_id} received stop signal — aborting.")
        raise TaskCancelled(f"Task {task_id} was stopped by user.")
