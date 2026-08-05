import logging

from core.models import Bug, PerformanceThreshold
from core.enums import BugSeverity

logger = logging.getLogger(__name__)


def check_performance_thresholds(test_run):
    """
    Inspect test_run.metadata['api_calls'] (already populated during
    execution — see tasks/execution.py) against the application's
    PerformanceThreshold and build Bug records for anything that breaches
    the warning/critical latency budget.

    Mirrors the ui_scanner.py convention: gather everything in memory
    first, only touch the DB at the end, and never raise — a failure here
    must never fail the underlying test run.
    """
    bugs_created = []

    try:
        test_case = test_run.test_case
        app = test_case.app if test_case else None
        if not app:
            return bugs_created

        api_calls = (test_run.metadata or {}).get('api_calls', [])
        if not api_calls:
            return bugs_created

        threshold = PerformanceThreshold.for_application(app)

        from tasks.discovery import get_url_pattern

        seen_keys = set()
        to_create = []

        for call in api_calls:
            latency = call.get('latency')
            if latency is None:
                continue

            url = call.get('url', '')
            method = call.get('method', 'GET')
            pattern = get_url_pattern(url, app.url)
            key = (method, pattern)
            if key in seen_keys:
                continue

            if latency >= threshold.api_latency_critical_ms:
                severity = BugSeverity.HIGH
                label = 'critical'
                limit = threshold.api_latency_critical_ms
            elif latency >= threshold.api_latency_warning_ms:
                severity = BugSeverity.MEDIUM
                label = 'warning'
                limit = threshold.api_latency_warning_ms
            else:
                continue

            seen_keys.add(key)
            to_create.append(Bug(
                application=app,
                test_run=test_run,
                bug_type='performance',
                severity=severity,
                title=f"[Slow Response] {method} {pattern} took {latency}ms",
                description=(
                    f"API call exceeded the {label} latency threshold "
                    f"({limit}ms) configured for this application.\n\n"
                    f"Method: {method}\nURL: {url}\nObserved latency: {latency}ms\n"
                    f"Threshold breached: {label} ({limit}ms)"
                ),
                status='open',
                steps_to_reproduce=[
                    f"Execute the test case that triggers {method} {pattern}",
                    f"Observe response latency: {latency}ms",
                    f"Compare against the configured {label} threshold of {limit}ms",
                ],
            ))

        if to_create:
            # Same savepoint isolation as web_vitals_scanner.py — never let a
            # constraint violation on a performance Bug poison a caller's
            # outer transaction.
            from django.db import transaction
            try:
                with transaction.atomic():
                    bugs_created = Bug.objects.bulk_create(to_create, batch_size=100)
            except Exception as db_err:
                logger.error(f"Performance bugs computed but failed to save: {db_err}")

    except Exception as e:
        logger.error(f"Performance threshold check failed for TestRun {getattr(test_run, 'id', '?')}: {e}")

    return bugs_created