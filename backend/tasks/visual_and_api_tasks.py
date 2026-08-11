"""
tasks/visual_and_api_tasks.py

Two Celery tasks:
  1. run_visual_regression  — triggered after a test run completes
  2. run_api_tests          — generates + executes API tests for an application
"""

import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='tasks.visual_and_api.run_visual_regression', queue='celery')
def run_visual_regression(self, test_run_id: int):
    """
    For every step result in the given test run that has a screenshot,
    compare it against the stored baseline for its page+step.

    Called automatically after execute_test() completes. You can also
    trigger it manually:
        run_visual_regression.delay(test_run_id)
    """
    from core.models import TestRun, TestResult, TestCase
    from services.visual_regression import compare_screenshot

    logger.info(f"[VisualTask] Starting visual regression for run {test_run_id}")

    try:
        test_run = TestRun.objects.select_related('test_case__app').get(id=test_run_id)
    except TestRun.DoesNotExist:
        logger.error(f"[VisualTask] TestRun {test_run_id} not found")
        return {'error': 'TestRun not found'}

    test_case = test_run.test_case
    app = test_case.app

    # Find which page this test case belongs to — match by URL in step data
    pages_by_url = {p.url: p for p in app.pages.all()}

    step_results = TestResult.objects.filter(
        test_run=test_run
    ).exclude(screenshot='').exclude(screenshot=None)

    results = []
    for step_result in step_results:
        screenshot_b64 = step_result.screenshot

        # Skip file path references (not base64)
        if screenshot_b64 and not screenshot_b64.startswith('/') and len(screenshot_b64) > 100:
            # Try to find a matching page for context
            # Use step 0 if no page found (safe fallback: one baseline per app)
            page = None
            steps = test_case.steps or []
            if step_result.step_number - 1 < len(steps):
                step_data = steps[step_result.step_number - 1]
                target = step_data.get('target', '') or step_data.get('selector', '')
                for url, pg in pages_by_url.items():
                    if url in target or target in url:
                        page = pg
                        break

            # Fall back to first page if no match
            if page is None and pages_by_url:
                page = list(pages_by_url.values())[0]

            if page is None:
                logger.warning(f"[VisualTask] No page found for step {step_result.step_number}, skipping")
                continue

            diff_result = compare_screenshot(
                test_run_id=test_run_id,
                page_id=page.id,
                step_number=step_result.step_number,
                screenshot_b64=screenshot_b64,
            )
            results.append({
                'step': step_result.step_number,
                **diff_result,
            })

            if diff_result['status'] == 'FAILED':
                logger.warning(
                    f"[VisualTask] Visual regression FAILED on step {step_result.step_number} "
                    f"— diff={diff_result['diff_percentage']}%"
                )

    summary = {
        'test_run_id': test_run_id,
        'steps_checked': len(results),
        'passed': sum(1 for r in results if r['status'] == 'PASSED'),
        'failed': sum(1 for r in results if r['status'] == 'FAILED'),
        'no_baseline': sum(1 for r in results if r['status'] == 'NO_BASELINE'),
    }
    logger.info(f"[VisualTask] Done: {summary}")
    return summary


@shared_task(bind=True, name='tasks.visual_and_api.run_api_tests', queue='celery')
def run_api_tests(self, app_id: int, auth_token: str = None, generate: bool = True):
    """
    1. (If generate=True) Use the LLM to create APITestCase rows for the app.
    2. Execute all APITestCase rows for the app and record results.

    Trigger manually:
        run_api_tests.delay(app_id, auth_token='your_jwt_here')
    Or from a view:
        run_api_tests.apply_async(args=[app_id], kwargs={'auth_token': token})
    """
    from core.models import Application, APITestCase, CeleryTask
    from services.api_test_service import APITestGenerator, APITestExecutor

    logger.info(f"[APITestTask] Starting for app {app_id}")

    try:
        app = Application.objects.get(id=app_id)
    except Application.DoesNotExist:
        logger.error(f"[APITestTask] Application {app_id} not found")
        return {'error': 'Application not found'}

    # Track in CeleryTask for the frontend progress UI
    celery_task, _ = CeleryTask.objects.update_or_create(
        task_id=self.request.id or f'api_test_{app_id}',
        defaults={
            'app': app,
            'task_type': 'api_tests',
            'status': 'progress',
            'progress': 0,
        }
    )

    generated_count = 0
    if generate:
        try:
            # Reuse the LLM client from existing llm_service
            from services.llm_service import LLMService
            llm = LLMService()
            generator = APITestGenerator(llm_service=llm)
        except Exception:
            generator = APITestGenerator(llm_service=None)

        new_cases = generator.generate(app)
        generated_count = len(new_cases)
        logger.info(f"[APITestTask] Generated {generated_count} test cases")

    celery_task.progress = 30
    celery_task.save(update_fields=['progress'])

    # Execute all API test cases
    executor = APITestExecutor(auth_token=auth_token)
    test_cases = list(APITestCase.objects.filter(application=app))

    if not test_cases:
        logger.info(f"[APITestTask] No API test cases to run for app {app_id}")
        celery_task.status = 'success'
        celery_task.progress = 100
        celery_task.save(update_fields=['status', 'progress'])
        return {'generated': generated_count, 'executed': 0, 'passed': 0, 'failed': 0}

    passed = failed = 0
    total = len(test_cases)

    for idx, test_case in enumerate(test_cases):
        try:
            run = executor.run(test_case)
            if run.passed:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            logger.exception(f"[APITestTask] Error running test {test_case.id}: {e}")
            failed += 1

        # Update progress
        progress = 30 + int(((idx + 1) / total) * 70)
        celery_task.progress = progress
        celery_task.save(update_fields=['progress'])

    celery_task.status = 'success'
    celery_task.progress = 100
    celery_task.save(update_fields=['status', 'progress'])

    summary = {
        'app_id': app_id,
        'generated': generated_count,
        'executed': total,
        'passed': passed,
        'failed': failed,
        'pass_rate': round((passed / total) * 100, 1) if total else 0,
    }
    logger.info(f"[APITestTask] Done: {summary}")
    return summary