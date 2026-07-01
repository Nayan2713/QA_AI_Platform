# backend/services/test_classifier.py

import logging
from core.models import TestCase, TestRun

logger = logging.getLogger(__name__)


class TestClassifier:
    @staticmethod
    def classify_test_case(test_case: TestCase) -> str:
        title_lower = test_case.title.lower()

        # FIX: 'workflow' and 'multi-step' matched too many AI-generated titles
        # (the generation prompt itself uses "workflow" language). Narrowed to
        # keywords that actually require agentic reasoning (payment flows,
        # ambiguous guest-checkout branching), not just multi-step CRUD.
        complex_keywords = ['checkout', 'payment', 'purchase', 'guest user']
        if any(kw in title_lower for kw in complex_keywords):
            logger.info(f"Classified '{test_case.title}' as BROWSER_USE (complex keyword).")
            return 'BROWSER_USE'

        steps = test_case.steps
        if isinstance(steps, list):
            # FIX: raised further — AI-generated suites routinely produce
            # 12-18 step tests for API-endpoint coverage; those are still
            # perfectly scriptable in Playwright and shouldn't pay the
            # agentic tax just for being long.
            if len(steps) > 20:
                logger.info(f"Classified '{test_case.title}' as BROWSER_USE (step count {len(steps)} > 20).")
                return 'BROWSER_USE'

        # FIX: require 2 of the last 3 runs to fail with a Playwright-style
        # error before escalating, not just 1. A single flaky failure
        # shouldn't permanently move a test to the slow engine.
        try:
            previous_runs = list(
                TestRun.objects.filter(test_case=test_case).order_by('-created_at')[:3]
            )
            # FIX: if the most recent run PASSED, trust that the test is
            # fixed — reset back to PLAYWRIGHT instead of being stuck on
            # BROWSER_USE forever because of an old failure.
            if previous_runs and previous_runs[0].status == 'COMPLETED':
                logger.info(f"Classified '{test_case.title}' as PLAYWRIGHT (most recent run passed).")
                return 'PLAYWRIGHT'

            playwright_error_kws = [
                'timeout', 'waiting for locator', 'selector',
                'element not found', 'not visible', 'not attached',
                'target closed', 'execution context'
            ]
            failure_hits = 0
            for run in previous_runs:
                if run.status == 'FAILED':
                    for res in run.step_results.filter(status='FAILED'):
                        err_msg = (res.error or '').lower()
                        if any(kw in err_msg for kw in playwright_error_kws):
                            failure_hits += 1
                            break  # count once per run, not once per step

            if failure_hits >= 2:
                logger.info(f"Classified '{test_case.title}' as BROWSER_USE ({failure_hits}/3 recent Playwright failures).")
                return 'BROWSER_USE'
        except Exception as e:
            logger.warning(f"Error checking historical runs for classification: {e}")

        logger.info(f"Classified '{test_case.title}' as PLAYWRIGHT.")
        return 'PLAYWRIGHT'
