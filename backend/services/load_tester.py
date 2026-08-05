import asyncio
import logging
import time

import httpx

logger = logging.getLogger(__name__)

# Mirrors the destructive-action caution in services/ui_scanner.py — never
# fire concurrent traffic at anything that isn't a safe, idempotent read.
_SAFE_METHODS = {'GET', 'HEAD'}


def _percentile(sorted_samples, pct):
    if not sorted_samples:
        return 0.0
    k = (len(sorted_samples) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(sorted_samples) - 1)
    if f == c:
        return sorted_samples[f]
    return sorted_samples[f] + (sorted_samples[c] - sorted_samples[f]) * (k - f)


import re

_BRACKETED_HOST_RE = re.compile(r'^\[([^\]]+)\](/.*)?$')


def _build_url(base_url, url_pattern):
    """
    APIEndpoint.url_pattern comes in three shapes (see tasks/discovery.py):
      - "/api/user/list/"                      — same host as the app
      - "[api.example.com]/api/user/list/"      — cross-subdomain endpoint,
        host explicitly bracketed because the bare path alone wouldn't say
        which host it belongs to
      - a full "https://..." URL (rare, kept as a fallback)
    """
    if url_pattern.startswith('http://') or url_pattern.startswith('https://'):
        return url_pattern

    bracketed = _BRACKETED_HOST_RE.match(url_pattern)
    if bracketed:
        host, path = bracketed.group(1), (bracketed.group(2) or '/')
        scheme = 'https' if base_url.startswith('https://') else 'http'
        return f"{scheme}://{host}{path}"

    if url_pattern.startswith('/'):
        return base_url.rstrip('/') + url_pattern

    # Unrecognized shape — treat as a path off the base host rather than
    # silently sending an invalid URL.
    return base_url.rstrip('/') + '/' + url_pattern


from tasks.cancellation import is_cancelled

async def _hit_endpoint(client, base_url, endpoint, concurrency, duration_seconds, task_id=None):
    """Fire concurrent requests at one endpoint for duration_seconds, using
    `concurrency` permanently-running workers rather than one big batch, so
    the test sustains load for the full window instead of bursting once."""
    url = _build_url(base_url, endpoint.url_pattern)
    latencies = []
    error_count = 0
    lock = asyncio.Lock()
    stop_at = time.monotonic() + duration_seconds

    async def worker():
        nonlocal error_count
        while time.monotonic() < stop_at:
            if task_id and is_cancelled(task_id):
                break
            start = time.monotonic()
            try:
                resp = await client.get(url, timeout=5.0)
                elapsed_ms = (time.monotonic() - start) * 1000
                async with lock:
                    latencies.append(elapsed_ms)
                    if resp.status_code >= 400:
                        error_count += 1
            except Exception:
                elapsed_ms = (time.monotonic() - start) * 1000
                async with lock:
                    latencies.append(elapsed_ms)
                    error_count += 1

    await asyncio.gather(*[worker() for _ in range(concurrency)])

    latencies.sort()
    total = len(latencies)
    return {
        "method": "GET",
        "url_pattern": endpoint.url_pattern,
        "api_endpoint_id": endpoint.id,
        "total_requests": total,
        "successful_requests": total - error_count,
        "error_rate": (error_count / total) if total else 0.0,
        "requests_per_second": (total / duration_seconds) if duration_seconds else 0.0,
        "p50_ms": _percentile(latencies, 50),
        "p95_ms": _percentile(latencies, 95),
        "p99_ms": _percentile(latencies, 99),
        "max_ms": latencies[-1] if latencies else 0.0,
    }


async def run_load_test(application, endpoints, concurrency=20, duration_seconds=30, task_id=None):
    """
    Fire `concurrency` concurrent workers at each of `endpoints` for
    `duration_seconds`, sequentially per endpoint (so N endpoints don't all
    compete for the same concurrency budget at once). Only GET/HEAD
    endpoints are tested — see _SAFE_METHODS.

    Returns a list of result dicts, one per endpoint tested. Never raises;
    an endpoint that errors out entirely just gets a 100% error_rate row
    rather than aborting the whole run.
    """
    results = []
    safe_endpoints = [e for e in endpoints if (e.method or 'GET').upper() in _SAFE_METHODS]

    async with httpx.AsyncClient(verify=False) as client:
        for endpoint in safe_endpoints:
            if task_id and is_cancelled(task_id):
                logger.info(f"Load test cancelled for task {task_id} before testing endpoint {endpoint.url_pattern}")
                break
            try:
                result = await _hit_endpoint(client, application.url, endpoint, concurrency, duration_seconds, task_id=task_id)
                results.append(result)
            except Exception as e:
                logger.error(f"Load test failed for endpoint {endpoint.url_pattern}: {e}")
                results.append({
                    "method": "GET",
                    "url_pattern": endpoint.url_pattern,
                    "api_endpoint_id": endpoint.id,
                    "total_requests": 0,
                    "successful_requests": 0,
                    "error_rate": 1.0,
                    "requests_per_second": 0.0,
                    "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "max_ms": 0.0,
                })

    return results