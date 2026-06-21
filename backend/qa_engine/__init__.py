# Monkeypatch redis-py 5.0+ to force RESP2 protocol on older Redis instances
# and disable maintenance notifications that require RESP3.
try:
    import redis.connection
    redis.connection.MaintNotificationsAbstractConnection._configure_maintenance_notifications = lambda *a, **k: None
    orig_init = redis.connection.Connection.__init__
    def patched_init(self, *args, **kwargs):
        if kwargs.get('protocol') is None:
            kwargs['protocol'] = 2
        orig_init(self, *args, **kwargs)
    redis.connection.Connection.__init__ = patched_init
except Exception:
    pass

# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from .celery import app as celery_app

__all__ = ('celery_app',)
