import json
import logging
import redis
from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.conf import settings

from .models import (
    Application, TestRun, Bug, CeleryTask, AgentSession
)

logger = logging.getLogger(__name__)

# OPTIMIZED: Use the central Redis client factory that enforces RESP2 protocol.
from qa_engine.redis_client import get_redis_client as _get_redis_client

def get_redis_client():
    return _get_redis_client()

def get_user_id_for_instance(instance):
    """
    Traverse models to find the user_id. Optimized to avoid N+1 queries.
    """
    try:
        if isinstance(instance, Application):
            return instance.user_id
        elif isinstance(instance, TestRun):
            return instance.test_case.app.user_id
        elif isinstance(instance, Bug):
            if instance.application_id:
                return instance.application.user_id
            elif instance.test_run_id:
                return instance.test_run.test_case.app.user_id
        elif isinstance(instance, AgentSession):
            return instance.application.user_id
        elif isinstance(instance, CeleryTask):
            r = get_redis_client()
            user_id = r.get(f"task_user:{instance.task_id}")
            if user_id:
                return int(user_id)
    except Exception as e:
        logger.error(f"Error resolving user_id for {instance}: {e}")
    return None

def publish_event(user_id, event_type, data):
    try:
        r = get_redis_client()
        payload = {
            "user_id": user_id,
            "type": event_type,
            "data": data
        }
        r.publish('qa_platform_events', json.dumps(payload))
    except Exception as e:
        logger.error(f"Failed to publish real-time event: {e}")

def register_task_user(task_id, user_id):
    """
    Map task_id to user_id in Redis so CeleryTask signals can resolve the user.
    """
    try:
        r = get_redis_client()
        r.setex(f"task_user:{task_id}", 86400, int(user_id))
    except Exception as e:
        logger.error(f"Failed to register task user: {e}")

def register_task_app(task_id, app_id):
    """
    Map task_id to app_id in Redis so we can track active tasks for applications.
    """
    try:
        r = get_redis_client()
        r.setex(f"task_app:{task_id}", 86400, int(app_id))
    except Exception as e:
        logger.error(f"Failed to register task app: {e}")

@receiver(post_save)
def model_post_save(sender, instance, created, **kwargs):
    # OPTIMIZED: Exclude bulk models (Page, TestCase, TestResult, APIEndpoint)
    # to avoid hundreds of DB queries and Redis connections during batch saves
    monitored_classes = (
        Application, TestRun, Bug, CeleryTask, AgentSession
    )
    if not isinstance(instance, monitored_classes):
        return
        
    user_id = get_user_id_for_instance(instance)
    if user_id is None:
        return
        
    model_name = instance.__class__.__name__.lower()
    action = "created" if created else "updated"
    event_type = f"{model_name}_{action}"
    
    data = {}
    if hasattr(instance, 'id'):
        data['id'] = instance.id
        
    # Serialize model-specific attributes for frontend state update
    if isinstance(instance, CeleryTask):
        data['task_id'] = instance.task_id
        data['task_type'] = instance.task_type
        data['status'] = instance.status
        data['progress'] = instance.progress
        data['result'] = instance.result
        data['error'] = instance.error
    elif isinstance(instance, TestRun):
        data['status'] = instance.status
        data['bugs_found'] = instance.bugs_found
        data['test_case_id'] = instance.test_case.id
        data['test_case_title'] = instance.test_case.title
    elif isinstance(instance, Application):
        data['status'] = instance.status
        data['login_status'] = instance.login_status
        data['login_error'] = instance.login_error
        data['page_count'] = instance.pages.count()
        data['api_count'] = instance.api_endpoints.count()
        data['test_case_count'] = instance.test_cases.count()
        data['bug_count'] = instance.bugs.count()
    elif isinstance(instance, Bug):
        data['title'] = instance.title
        data['severity'] = instance.severity
        data['status'] = instance.status
        data['app_id'] = instance.application_id or (instance.test_run.test_case.app_id if instance.test_run else None)
        
    publish_event(user_id, event_type, data)

@receiver(post_delete)
def model_post_delete(sender, instance, **kwargs):
    monitored_classes = (
        Application, TestRun, Bug, CeleryTask, AgentSession
    )
    if not isinstance(instance, monitored_classes):
        return
        
    user_id = get_user_id_for_instance(instance)
    if user_id is None:
        return
        
    model_name = instance.__class__.__name__.lower()
    event_type = f"{model_name}_deleted"
    
    data = {}
    if hasattr(instance, 'id'):
        data['id'] = instance.id
    if isinstance(instance, CeleryTask):
        data['task_id'] = instance.task_id
        
    publish_event(user_id, event_type, data)


@receiver(pre_delete, sender=Application)
def application_pre_delete(sender, instance, **kwargs):
    """
    When an Application is deleted, find and stop/revoke all active Celery tasks
    associated with it in Redis.
    """
    from qa_engine.celery import app as celery_app
    
    try:
        r = get_redis_client()
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match='task_app:*', count=200)
            for key in keys:
                val = r.get(key)
                if val and int(val) == instance.id:
                    task_id = key.decode().replace('task_app:', '', 1)
                    # Set cooperative stop flag and revoke Celery task safely across OS platforms
                    from tasks.cancellation import set_stop_flag
                    set_stop_flag(task_id)
                    try:
                        celery_app.control.revoke(task_id, terminate=True, signal='SIGTERM')
                    except Exception:
                        pass
                    
                    # Update task status in database
                    try:
                        task = CeleryTask.objects.filter(task_id=task_id).first()
                        if task and task.status in ['pending', 'progress']:
                            task.status = 'failed'
                            task.error = "Application deleted by user."
                            task.save()
                    except Exception as db_err:
                        logger.error(f"Failed to update database status for revoked task {task_id}: {db_err}")
            if cursor == 0:
                break
    except Exception as e:
        logger.error(f"Error revoking tasks during application pre_delete: {e}")
