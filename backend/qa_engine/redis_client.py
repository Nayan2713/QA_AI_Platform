# backend/qa_engine/redis_client.py

"""Central Redis client factory — always enforces RESP2 protocol when redis-py v5+ is present.

Every part of the codebase that needs a Redis connection should use
``get_redis_client()`` instead of constructing one directly.  This
avoids the ``unknown command HELLO`` crash on Redis servers that do
not support the RESP3 handshake introduced in redis-py 5.x, while remaining
backwards-compatible with older redis-py versions (like 4.x) which do not
accept the ``protocol`` parameter.
"""

import redis
from django.conf import settings
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

_pool: redis.ConnectionPool | None = None


def get_redis_client(url: str | None = None) -> redis.Redis:
    """Return a Redis client using RESP2 protocol if supported.

    Parameters
    ----------
    url : str, optional
        Redis URL.  Defaults to ``settings.CELERY_BROKER_URL``.

    A module-level connection pool is reused across calls so that
    signal handlers and SSE views share the same pool rather than
    opening a new TCP socket on every event.
    """
    global _pool
    target_url = url or getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")

    # Check redis-py version
    try:
        version_parts = [int(p) for p in redis.__version__.split('.') if p.isdigit()]
    except Exception:
        version_parts = []
    
    is_redis_v5 = version_parts and version_parts[0] >= 5

    # If it's not redis v5, we must strip the protocol parameter from the connection URL
    if not is_redis_v5:
        parsed = urlparse(target_url)
        query = dict(parse_qsl(parsed.query))
        if 'protocol' in query:
            del query['protocol']
            new_query = urlencode(query)
            target_url = urlunparse((
                parsed.scheme, parsed.netloc, parsed.path,
                parsed.params, new_query, parsed.fragment
            ))

    if _pool is None:
        if is_redis_v5:
            _pool = redis.ConnectionPool.from_url(target_url, protocol=2)
        else:
            _pool = redis.ConnectionPool.from_url(target_url)

    if is_redis_v5:
        return redis.Redis(connection_pool=_pool, protocol=2)
    else:
        return redis.Redis(connection_pool=_pool)
