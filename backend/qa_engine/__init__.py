# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from .celery import app as celery_app

# Fix Python 3.14 compatibility issue with Django template context copying
try:
    import sys
    from django.template import context
    def _patched_base_context_copy(self):
        duplicate = object.__new__(self.__class__)
        duplicate.__dict__.update(self.__dict__)
        duplicate.dicts = self.dicts[:]
        return duplicate
    context.BaseContext.__copy__ = _patched_base_context_copy
except Exception:
    pass

__all__ = ('celery_app',)
