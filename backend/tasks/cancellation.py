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

import logging
import threading
from qa_engine.redis_client import get_redis_client

logger = logging.getLogger(__name__)

STOP_FLAG_TTL = 3600  # seconds — auto-expires so Redis stays clean

_active_handles = {}  # {task_id: [handle1, handle2, ...]}
_handles_lock = threading.Lock()


def register_active_handle(task_id: str, handle: any) -> None:
    """Register an active Playwright page/context/loop handle for instant cancellation."""
    if not task_id or not handle:
        return
    with _handles_lock:
        if task_id not in _active_handles:
            _active_handles[task_id] = []
        if handle not in _active_handles[task_id]:
            _active_handles[task_id].append(handle)


def unregister_active_handle(task_id: str, handle: any = None) -> None:
    """Remove registered handle when task finishes."""
    if not task_id:
        return
    with _handles_lock:
        if handle:
            if task_id in _active_handles:
                _active_handles[task_id] = [h for h in _active_handles[task_id] if h != handle]
                if not _active_handles[task_id]:
                    del _active_handles[task_id]
        else:
            _active_handles.pop(task_id, None)


def abort_active_handles(task_id: str) -> None:
    """Close active Playwright pages/contexts/loops registered for this task_id to break blocking calls immediately."""
    if not task_id:
        return
    handles = []
    with _handles_lock:
        handles = list(_active_handles.get(task_id, []))
        _active_handles.pop(task_id, None)
    
    for h in handles:
        try:
            # Playwright Page / Context close
            if hasattr(h, 'close') and callable(h.close):
                try:
                    h.close()
                    logger.info(f"[CANCELLATION] Force-closed Playwright page/context for task {task_id}")
                except Exception:
                    pass
            # Asyncio loop abort
            elif hasattr(h, 'call_soon_threadsafe') and callable(h.call_soon_threadsafe):
                try:
                    def _cancel_loop_tasks():
                        import asyncio
                        for t in asyncio.all_tasks(h):
                            t.cancel()
                    h.call_soon_threadsafe(_cancel_loop_tasks)
                    logger.info(f"[CANCELLATION] Cancelled asyncio tasks for task {task_id}")
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[CANCELLATION] Error aborting active handle for {task_id}: {e}")


class TaskCancelled(Exception):
    """Raised inside a task when a stop flag is detected."""
    pass


def set_stop_flag(task_id: str) -> None:
    """Set the stop flag for a task and immediately abort any active Playwright/async handles."""
    try:
        r = get_redis_client()
        r.setex(f"stop_flag:{task_id}", STOP_FLAG_TTL, "1")
        logger.info(f"[CANCELLATION] Stop flag set for task {task_id}")
    except Exception as e:
        logger.error(f"[CANCELLATION] Failed to set stop flag for {task_id}: {e}")

    # Immediately close any registered Playwright pages/contexts for this task_id
    abort_active_handles(task_id)


def clear_stop_flag(task_id: str) -> None:
    """Remove the stop flag and unregister handles. Called when a task ends."""
    try:
        r = get_redis_client()
        r.delete(f"stop_flag:{task_id}")
    except Exception as e:
        logger.warning(f"[CANCELLATION] Failed to clear stop flag for {task_id}: {e}")
    unregister_active_handle(task_id)


def is_cancelled(task_id: str) -> bool:
    """Returns True if a stop flag has been set for this task (checks Redis & DB fallback)."""
    if not task_id:
        return False
        
    try:
        r = get_redis_client()
        if r.exists(f"stop_flag:{task_id}") == 1:
            return True
    except Exception as e:
        logger.warning(f"[CANCELLATION] Redis check failed for {task_id}: {e}")

    # Database fallback: check if CeleryTask was marked stopped/cancelled/failed in DB
    try:
        from core.models import CeleryTask
        ct = CeleryTask.objects.filter(task_id=str(task_id)).first()
        if ct:
            if ct.status in ['failed', 'cancelled'] and (ct.error and 'stop' in ct.error.lower()):
                return True
    except Exception:
        pass

    return False


def check_cancelled(task_id: str) -> None:
    """
    Raise TaskCancelled if this task has been asked to stop.
    Call this at every major checkpoint inside a task.
    """
    if is_cancelled(task_id):
        logger.info(f"[CANCELLATION] Task {task_id} received stop signal — aborting.")
        raise TaskCancelled(f"Task {task_id} was stopped by user.")


def revoke_celery_task(task_id: str) -> None:
    """
    Safely revoke a Celery task without passing terminate=True.
    Passing terminate=True causes NotImplementedError on thread pools (-P threads).
    Cooperative cancellation via set_stop_flag handles stopping active threads.
    """
    try:
        from qa_engine.celery import app as celery_app
        celery_app.control.revoke(task_id, terminate=False)
        logger.info(f"[CANCELLATION] Safely revoked Celery task {task_id}")
    except Exception as e:
        logger.warning(f"[CANCELLATION] Failed to revoke task {task_id}: {e}")

