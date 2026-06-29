import logging
from core.models import TestCase, TestRun

logger = logging.getLogger(__name__)

class TestClassifier:
    @staticmethod
    def classify_test_case(test_case: TestCase) -> str:
        """
        Classifies whether a test case should be executed via Playwright or BrowserUseAgent.
        Returns: 'PLAYWRIGHT' or 'BROWSER_USE'
        """
        title_lower = test_case.title.lower()
        
        # 1. Always use Browser-Use Agent for complex multi-step workflows or specific checkout/signups
        complex_keywords = ['checkout', 'payment', 'workflow', 'complex', 'purchase', 'guest user', 'adaptive']
        if any(kw in title_lower for kw in complex_keywords):
            logger.info(f"Classified test '{test_case.title}' as BROWSER_USE due to complex workflow keywords.")
            return 'BROWSER_USE'
            
        # 2. Check steps count and actions. If there are custom dropdowns or hover/scroll actions,
        # or if the test has more than 6 steps, use Browser-Use.
        steps = test_case.steps
        if isinstance(steps, list):
            if len(steps) > 6:
                logger.info(f"Classified test '{test_case.title}' as BROWSER_USE because step count ({len(steps)}) exceeds standard threshold.")
                return 'BROWSER_USE'
                
            for step in steps:
                action = step.get('action', '').lower()
                # Use Agent for hover or select dropdown actions if they seem dynamic
                if action in ['hover', 'select']:
                    logger.info(f"Classified test '{test_case.title}' as BROWSER_USE due to dynamic action '{action}'.")
                    return 'BROWSER_USE'
                    
        # 3. Check historical runs: if this test case previously failed with selector timeouts
        # or playwright crashes, we elevate it to BROWSER_USE so the AI can heal it.
        try:
            previous_runs = TestRun.objects.filter(test_case=test_case).order_by('-created_at')[:3]
            for run in previous_runs:
                if run.status == 'FAILED':
                    # Check if there were playwright selector/timeout errors in step results
                    for res in run.step_results.filter(status='FAILED'):
                        err_msg = (res.error or '').lower()
                        if 'timeout' in err_msg or 'waiting for locator' in err_msg or 'selector' in err_msg:
                            logger.info(
                                f"Classified test '{test_case.title}' as BROWSER_USE "
                                f"due to previous Playwright timeout/selector failure: {res.error[:80]}..."
                            )
                            return 'BROWSER_USE'
        except Exception as e:
            logger.warning(f"Error checking historical test runs for classification: {e}")

        # 4. Default to raw PLAYWRIGHT for simple, stable, and fast executions
        logger.info(f"Classified test '{test_case.title}' as PLAYWRIGHT.")
        return 'PLAYWRIGHT'
