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
import redis.asyncio as aioredis
from django.conf import settings
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

_pool: redis.ConnectionPool | None = None
_async_pool: aioredis.ConnectionPool | None = None


def _resolve_url(url: str) -> str:
    """If url specifies an unresolvable hostname (e.g. 'redis' outside Docker), fallback to 127.0.0.1."""
    import socket
    try:
        parsed = urlparse(url)
        if parsed.hostname:
            try:
                socket.getaddrinfo(parsed.hostname, parsed.port or 6379)
            except socket.gaierror:
                new_netloc = parsed.netloc.replace(parsed.hostname, '127.0.0.1', 1)
                url = urlunparse((parsed.scheme, new_netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    except Exception:
        pass
    return url


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
    raw_url = url or getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
    target_url = _resolve_url(raw_url)

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

    return redis.Redis(connection_pool=_pool)


def get_async_redis_client(url: str | None = None) -> aioredis.Redis:
    """Return an async Redis client using RESP2 protocol if supported.

    A module-level async connection pool is reused across calls.
    """
    global _async_pool
    raw_url = url or getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
    target_url = _resolve_url(raw_url)

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

    if _async_pool is None:
        if is_redis_v5:
            _async_pool = aioredis.ConnectionPool.from_url(target_url, protocol=2)
        else:
            _async_pool = aioredis.ConnectionPool.from_url(target_url)

    return aioredis.Redis(connection_pool=_async_pool)
