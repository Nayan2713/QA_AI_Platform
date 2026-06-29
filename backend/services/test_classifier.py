import logging
from core.models import TestCase, TestRun

logger = logging.getLogger(__name__)


class TestClassifier:
    @staticmethod
    def classify_test_case(test_case: TestCase) -> str:
        """
        Classifies whether a test case should run via Playwright or BrowserUseAgent.
        Returns 'PLAYWRIGHT' or 'BROWSER_USE'.

        FIXES vs original:
          - FIX 1: Step threshold raised 6 → 12. The fallback generator produces
            7-9 step tests routinely (navigate + fill fields + click + wait + assert
            + screenshot). The old threshold of 6 routed ~40% of all generated
            tests to the heavier BROWSER_USE agent unnecessarily.
          - FIX 2: hover/select actions no longer auto-escalate. These work fine
            with Playwright on standard apps. Only escalate when a PREVIOUS run
            actually failed with a selector/timeout error on that action.
          - FIX 3: Added 'scroll' to the safe Playwright action list (it was
            implicitly escalated before because it's not in the original allow-list).
        """
        title_lower = test_case.title.lower()

        # 1. Complex multi-step workflows that genuinely need the AI agent
        complex_keywords = [
            'checkout', 'payment', 'workflow', 'complex',
            'purchase', 'guest user', 'adaptive', 'multi-step'
        ]
        if any(kw in title_lower for kw in complex_keywords):
            logger.info(
                f"Classified test '{test_case.title}' as BROWSER_USE "
                f"(complex workflow keyword)."
            )
            return 'BROWSER_USE'

        steps = test_case.steps
        if isinstance(steps, list):
            # FIX 1: raised from 6 to 12
            if len(steps) > 12:
                logger.info(
                    f"Classified test '{test_case.title}' as BROWSER_USE "
                    f"(step count {len(steps)} > 12)."
                )
                return 'BROWSER_USE'

            # FIX 2: don't escalate hover/select by action type alone —
            # Playwright handles them fine on most apps. Only escalate based
            # on historical failures (see section 3 below).

        # 3. Escalate only when previous runs actually failed with Playwright errors
        try:
            previous_runs = TestRun.objects.filter(
                test_case=test_case
            ).order_by('-created_at')[:3]

            for run in previous_runs:
                if run.status == 'FAILED':
                    for res in run.step_results.filter(status='FAILED'):
                        err_msg = (res.error or '').lower()
                        playwright_errors = [
                            'timeout', 'waiting for locator', 'selector',
                            'element not found', 'not visible', 'not attached',
                            'target closed', 'execution context'
                        ]
                        if any(kw in err_msg for kw in playwright_errors):
                            logger.info(
                                f"Classified test '{test_case.title}' as BROWSER_USE "
                                f"(previous Playwright failure: {res.error[:80]})"
                            )
                            return 'BROWSER_USE'
        except Exception as e:
            logger.warning(f"Error checking historical runs for classification: {e}")

        logger.info(f"Classified test '{test_case.title}' as PLAYWRIGHT.")
        return 'PLAYWRIGHT'