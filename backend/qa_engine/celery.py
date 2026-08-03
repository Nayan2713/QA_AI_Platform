import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'qa_engine.settings')

app = Celery('qa_engine')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Explicitly import root tasks modules so Celery registers them on boot
app.conf.imports = (
    'tasks.discovery',
    'tasks.test_generation',
    'tasks.execution',
    'tasks.bug_detection',
    'tasks.quality_check',
    'tasks.bulk_upload',
)

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


from celery.signals import task_prerun, task_postrun, task_failure
from django.db import close_old_connections, connections

@task_prerun.connect
def cleanup_db_connections_prerun(*args, **kwargs):
    close_old_connections()

@task_postrun.connect
def cleanup_db_connections_postrun(*args, **kwargs):
    close_old_connections()
    connections.close_all()

@task_failure.connect
def cleanup_db_connections_failure(*args, **kwargs):
    close_old_connections()
    connections.close_all()

