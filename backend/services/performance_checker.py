# backend/services/performance_checker.py
import logging
from core.models import PerformanceThreshold, Bug, APIEndpoint
from core.enums import BugSeverity

logger = logging.getLogger(__name__)

def check_performance_thresholds(test_run):
    """
    Checks API call latencies recorded in test_run.metadata against PerformanceThreshold.
    Bulk-creates performance Bug objects only after full inspection succeeds.
    """
    if not test_run or not test_run.test_case or not test_run.metadata or not isinstance(test_run.metadata, dict):
        return []

    api_calls = test_run.metadata.get('api_calls', [])
    if not api_calls:
        return []

    app = test_run.test_case.app
    threshold = PerformanceThreshold.objects.filter(application=app).first()
    if not threshold:
        threshold = PerformanceThreshold.objects.filter(application__isnull=True).first()

    warning_ms = threshold.api_latency_warning_ms if threshold else 500
    critical_ms = threshold.api_latency_critical_ms if threshold else 2000

    bugs_to_create = []
    seen_keys = set()

    for call in api_calls:
        if not isinstance(call, dict):
            continue
        latency = call.get('latency', 0)
        if latency <= warning_ms:
            continue

        method = (call.get('method') or 'GET').upper()
        url = call.get('url') or 'Unknown URL'
        key = (method, url)

        # Avoid duplicate bugs in same run for exact same method + url
        if key in seen_keys:
            continue
        seen_keys.add(key)

        is_critical = latency >= critical_ms
        severity = BugSeverity.HIGH if is_critical else BugSeverity.MEDIUM
        threshold_exceeded = critical_ms if is_critical else warning_ms

        title = f"[Slow Response] {method} {url} took {latency}ms"
        description = (
            f"API Endpoint latency breached performance threshold.\n\n"
            f"Observed Latency: {latency}ms\n"
            f"Exceeded Threshold: {threshold_exceeded}ms ({'Critical' if is_critical else 'Warning'})\n"
            f"HTTP Method: {method}\n"
            f"URL: {url}\n"
            f"Status Code: {call.get('status', 'N/A')}"
        )

        steps = [
            f"1. Issue {method} request to {url}",
            f"2. Measure response time (Observed: {latency}ms)",
            f"3. Assert response time is under {threshold_exceeded}ms threshold"
        ]

        # Link API endpoint if match found
        api_ep = APIEndpoint.objects.filter(application=app, method=method, url_pattern=url).first()

        bug = Bug(
            application=app,
            test_run=test_run,
            bug_type='performance',
            severity=severity,
            title=title,
            description=description,
            steps_to_reproduce=steps,
            api_endpoint=api_ep,
            status='open'
        )
        bugs_to_create.append(bug)

    if bugs_to_create:
        created_bugs = Bug.objects.bulk_create(bugs_to_create)
        logger.info(f"Created {len(created_bugs)} performance threshold bug(s) for TestRun #{test_run.id}")
        return created_bugs

    return []
