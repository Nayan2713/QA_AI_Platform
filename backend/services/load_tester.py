# backend/services/load_tester.py
import asyncio
import time
import logging
from typing import List, Dict, Any, Optional
import httpx
from core.models import APIEndpoint, LoadTestResult

logger = logging.getLogger(__name__)

_DESTRUCTIVE_KEYWORDS = [
    'delete', 'remove', 'unsubscribe', 'deactivat', 'terminate', 'cancel',
    'destroy', 'drop', 'purge', 'reset', 'logout', 'signout', 'pay', 'checkout'
]

def _is_safe_endpoint(endpoint: APIEndpoint) -> bool:
    method = (endpoint.method or 'GET').upper()
    if method not in ('GET', 'HEAD', 'OPTIONS'):
        return False
    pattern = (endpoint.url_pattern or '').lower()
    return not any(kw in pattern for kw in _DESTRUCTIVE_KEYWORDS)

def _percentile(data: List[float], percent: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (percent / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return float(sorted_data[-1])
    d0 = sorted_data[f] * (c - k)
    d1 = sorted_data[c] * (k - f)
    return float(d0 + d1)

async def _worker(client: httpx.AsyncClient, url: str, method: str, end_time: float, latencies: List[float], errors: List[int]):
    while time.time() < end_time:
        start = time.time()
        try:
            res = await client.request(method, url, timeout=10.0)
            latency_ms = (time.time() - start) * 1000.0
            latencies.append(latency_ms)
            if res.status_code >= 400:
                errors.append(res.status_code)
        except Exception:
            latency_ms = (time.time() - start) * 1000.0
            latencies.append(latency_ms)
            errors.append(500)

async def run_load_test(app, endpoints: Optional[List[APIEndpoint]] = None, concurrency: int = 20, duration_seconds: int = 30) -> List[Dict[str, Any]]:
    """
    Executes concurrent load testing against safe GET endpoints of the application using httpx.
    Gathers all metrics in memory first. Returns a list of metric dicts.
    """
    if not endpoints:
        all_endpoints = list(APIEndpoint.objects.filter(application=app))
        endpoints = [ep for ep in all_endpoints if _is_safe_endpoint(ep)]
        if not endpoints and app.url:
            # Fallback to app root URL if no specific safe API endpoints stored
            dummy_ep, _ = APIEndpoint.objects.get_or_create(
                application=app,
                method='GET',
                url_pattern=app.url
            )
            endpoints = [dummy_ep]

    if not endpoints:
        logger.warning(f"No safe endpoints available for load test on app #{app.id}")
        return []

    results = []
    headers = {"User-Agent": "QA-AI-Platform-LoadTester/1.0"}

    # Add auth storage state if login_status is LOGGED_IN
    if getattr(app, 'storage_state', None):
        headers["X-Test-Storage-State"] = "active"

    async with httpx.AsyncClient(headers=headers, verify=False) as client:
        for ep in endpoints:
            url = ep.url_pattern
            if not url.startswith('http://') and not url.startswith('https://'):
                base = app.base_url or app.url
                url = f"{base.rstrip('/')}/{url.lstrip('/')}"

            latencies: List[float] = []
            errors: List[int] = []

            end_time = time.time() + duration_seconds
            start_wall = time.time()

            tasks = [
                _worker(client, url, ep.method or 'GET', end_time, latencies, errors)
                for _ in range(concurrency)
            ]
            await asyncio.gather(*tasks)

            total_elapsed = max(time.time() - start_wall, 0.001)
            total_reqs = len(latencies)
            failed_reqs = len(errors)
            error_rate = (failed_reqs / total_reqs) if total_reqs > 0 else 0.0
            rps = total_reqs / total_elapsed

            p50 = _percentile(latencies, 50)
            p95 = _percentile(latencies, 95)
            p99 = _percentile(latencies, 99)

            results.append({
                'application': app,
                'api_endpoint': ep,
                'concurrency': concurrency,
                'total_requests': total_reqs,
                'p50_ms': round(p50, 2),
                'p95_ms': round(p95, 2),
                'p99_ms': round(p99, 2),
                'error_rate': round(error_rate, 4),
                'requests_per_second': round(rps, 2)
            })

    return results
