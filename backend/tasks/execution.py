import logging
import base64
from celery import shared_task
from django.db import transaction
from playwright.sync_api import sync_playwright

from core.models import TestRun, TestResult, TestCase

logger = logging.getLogger(__name__)

@shared_task(name="tasks.execution.execute_test")
def execute_test(test_run_id):
    """
    Celery task that executes a TestCase step-by-step using Playwright.
    Captures screenshots on failure, records step status, and triggers bug detection.
    """
    logger.info(f"Starting test execution task for TestRun ID: {test_run_id}")
    
    try:
        test_run = TestRun.objects.get(id=test_run_id)
    except TestRun.DoesNotExist:
        logger.error(f"TestRun with ID {test_run_id} does not exist.")
        return {"error": f"TestRun with ID {test_run_id} not found."}

    test_case = test_run.test_case
    test_run.status = 'RUNNING'
    test_run.save()

    # Clear previous results
    TestResult.objects.filter(test_run=test_run).delete()

    steps = test_case.steps
    total_steps = len(steps)
    passed_steps = 0
    run_failed = False

    with sync_playwright() as p:
        try:
            # Launch browser
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                ignore_https_errors=True
            )
            page = context.new_page()
            # Set default timeout to 5 seconds to keep execution fast
            page.set_default_timeout(5000)
            
            for index, step in enumerate(steps):
                step_num = index + 1
                action = step.get("action")
                selector = step.get("selector", "")
                target = step.get("target", "")
                value = step.get("value", "")
                
                logger.info(f"Running step {step_num}/{total_steps}: {action} | Selector: '{selector}' | Target: '{target}' | Value: '{value}'")
                
                step_passed = True
                error_msg = None
                screenshot_b64 = None
                
                try:
                    if action == "navigate":
                        if not target:
                            raise ValueError("Navigation action requires a target URL")
                        page.goto(target, wait_until="load")
                        
                    elif action == "fill":
                        if not selector:
                            raise ValueError("Fill action requires a selector")
                        # Ensure visibility before filling
                        page.locator(selector).first.wait_for(state="visible", timeout=3000)
                        page.locator(selector).first.fill(value)
                        
                    elif action == "click":
                        if not selector:
                            raise ValueError("Click action requires a selector")
                        page.locator(selector).first.wait_for(state="visible", timeout=3000)
                        page.locator(selector).first.click()
                        
                    elif action == "wait":
                        wait_ms = int(value) if value.isdigit() else 1000
                        page.wait_for_timeout(wait_ms)
                        
                    elif action == "assert":
                        # If a selector is provided, look in it. Otherwise look in the entire body.
                        if selector:
                            page.locator(selector).first.wait_for(state="visible", timeout=3000)
                            content = page.locator(selector).first.inner_text()
                        else:
                            content = page.locator("body").inner_text()
                            
                        if value.lower() not in content.lower():
                            raise AssertionError(f"Assertion failed: Expected '{value}' to be present, but found: '{content[:100]}...'")
                    
                    else:
                        raise ValueError(f"Unknown action type: {action}")
                        
                except Exception as e:
                    step_passed = False
                    run_failed = True
                    error_msg = str(e)
                    logger.error(f"Step {step_num} failed: {error_msg}")
                    
                    # Capture screenshot on failure
                    try:
                        screenshot_bytes = page.screenshot(type="png", full_page=False)
                        screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                    except Exception as screenshot_err:
                        logger.error(f"Failed to capture screenshot: {screenshot_err}")
                
                if step_passed:
                    passed_steps += 1
                
                # Save step result
                TestResult.objects.create(
                    test_run=test_run,
                    step_number=step_num,
                    status='PASSED' if step_passed else 'FAILED',
                    error=error_msg,
                    screenshot=screenshot_b64
                )
                
            browser.close()
            
        except Exception as global_err:
            run_failed = True
            logger.error(f"Global Playwright runner error: {global_err}")
            TestResult.objects.create(
                test_run=test_run,
                step_number=1 if total_steps == 0 else total_steps,
                status='FAILED',
                error=f"Playwright Execution Crash: {str(global_err)}"
            )

    # Save overall metrics
    test_run.status = 'FAILED' if run_failed else 'COMPLETED'
    test_run.metadata = {
        "passed_steps": passed_steps,
        "total_steps": total_steps,
    }
    test_run.save()

    # Trigger Bug Detection task asynchronously
    from tasks.bug_detection import detect_bugs
    detect_bugs.delay(test_run.id)

    return {
        "status": test_run.status,
        "passed_steps": passed_steps,
        "total_steps": total_steps
    }
