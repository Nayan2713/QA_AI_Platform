import logging
import base64
import threading
from django.utils import timezone
from celery import shared_task
from django.db import transaction
from playwright.sync_api import sync_playwright

from core.models import TestRun, TestResult, TestCase, CeleryTask

logger = logging.getLogger(__name__)

def run_in_thread(func, *args, **kwargs):
    """
    Runs a function inside a separate thread to bypass Django's SynchronousOnlyOperation check.
    Closes the thread's DB connection afterwards to prevent connection leaks.
    """
    res = []
    err = []
    def target():
        from django.db import connection
        try:
            res.append(func(*args, **kwargs))
        except Exception as e:
            err.append(e)
        finally:
            connection.close()
            
    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    if err:
        raise err[0]
    return res[0]

@shared_task(bind=True, name="tasks.execution.execute_test")
def execute_test(self, test_run_id):
    """
    Celery task that executes a TestCase step-by-step using Playwright,
    tracking task progress in the CeleryTask registry.
    """
    logger.info(f"Starting test execution task for TestRun ID: {test_run_id}")
    
    # Create/update task tracking record (runs in celery thread before Playwright is started)
    task_id = self.request.id or "dummy_task_id"
    
    def get_or_create_task():
        obj, created = CeleryTask.objects.get_or_create(
            task_id=task_id,
            defaults={
                'task_type': 'execution',
                'status': 'progress',
                'progress': 10,
                'result': {"status_text": "Starting test execution run..."}
            }
        )
        if not created:
            obj.status = 'progress'
            obj.progress = 10
            obj.result = {"status_text": "Starting test execution run..."}
            obj.save()
        return obj

    task_record = run_in_thread(get_or_create_task)
    
    try:
        try:
            test_run = run_in_thread(TestRun.objects.get, id=test_run_id)
        except TestRun.DoesNotExist:
            logger.error(f"TestRun with ID {test_run_id} does not exist.")
            def handle_missing_run():
                task_record.status = 'failed'
                task_record.error = f"TestRun with ID {test_run_id} not found."
                task_record.completed_at = timezone.now()
                task_record.save()
            run_in_thread(handle_missing_run)
            return {"error": f"TestRun with ID {test_run_id} not found."}

        test_case = run_in_thread(lambda: test_run.test_case)
        
        def init_test_run():
            test_run.status = 'RUNNING'
            test_run.save()
            # Clear previous results
            TestResult.objects.filter(test_run=test_run).delete()
        run_in_thread(init_test_run)

        steps = test_case.steps
        total_steps = len(steps)
        passed_steps = 0
        run_failed = False
        api_logs = []

        with sync_playwright() as p:
            try:
                # Launch browser
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    ignore_https_errors=True
                )
                page = context.new_page()
                
                # Register background API response listener
                def capture_network_api(response):
                    try:
                        resource_type = response.request.resource_type
                        if resource_type in ['xhr', 'fetch']:
                            api_logs.append({
                                "method": response.request.method,
                                "url": response.url,
                                "status": response.status
                            })
                    except Exception as net_err:
                        logger.error(f"Error logging network response: {net_err}")

                page.on("response", capture_network_api)
                
                # Set default timeout to 15 seconds to allow slower websites to load
                page.set_default_timeout(15000)
                
                for index, step in enumerate(steps):
                    step_num = index + 1
                    action = step.get("action")
                    selector = step.get("selector", "")
                    target = step.get("target", "")
                    value = step.get("value", "")
                    
                    logger.info(f"Running step {step_num}/{total_steps}: {action} | Selector: '{selector}' | Target: '{target}' | Value: '{value}'")
                    
                    # Update progress in a thread
                    def update_step_progress():
                        task_record.progress = int(10 + (step_num / total_steps) * 80)
                        details = f"target '{target}'" if action == "navigate" else f"selector '{selector}'"
                        task_record.result = {
                            "status_text": f"Running step {step_num}/{total_steps}: {action.upper()} {details}",
                            "step_number": step_num,
                            "total_steps": total_steps
                        }
                        task_record.save()
                    run_in_thread(update_step_progress)

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
                            page.locator(selector).first.wait_for(state="visible", timeout=5000)
                            page.locator(selector).first.fill(value)
                            
                        elif action == "click":
                            if not selector:
                                raise ValueError("Click action requires a selector")
                            page.locator(selector).first.wait_for(state="visible", timeout=5000)
                            page.locator(selector).first.click()
                            
                        elif action == "wait":
                            wait_ms = int(value) if value.isdigit() else 1000
                            page.wait_for_timeout(wait_ms)
                            
                        elif action == "assert":
                            # If a selector is provided, look in it. Otherwise look in the entire body.
                            if selector:
                                page.locator(selector).first.wait_for(state="visible", timeout=5000)
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
                    
                    # Save step result in a thread
                    def create_step_result(step_passed_local, error_msg_local, screenshot_b64_local):
                        TestResult.objects.create(
                            test_run=test_run,
                            step_number=step_num,
                            status='PASSED' if step_passed_local else 'FAILED',
                            error=error_msg_local,
                            screenshot=screenshot_b64_local
                        )
                    run_in_thread(create_step_result, step_passed, error_msg, screenshot_b64)
                    
                    if not step_passed:
                        logger.warning(f"Aborting execution at step {step_num} due to failure.")
                        break
                    
                # Inspect background API log calls for status code errors (status >= 400)
                failed_apis = [log for log in api_logs if log['status'] >= 400]
                if failed_apis:
                    run_failed = True
                    error_details = "\n".join([
                        f"- {log['method']} {log['url']} -> Status {log['status']}"
                        for log in failed_apis
                    ])
                    def log_api_failures():
                        TestResult.objects.create(
                            test_run=test_run,
                            step_number=total_steps + 1,
                            status='FAILED',
                            error=f"API Network Failures Detected:\n{error_details}"
                        )
                    run_in_thread(log_api_failures)
                    total_steps += 1

                browser.close()
                
            except Exception as global_err:
                run_failed = True
                logger.error(f"Global Playwright runner error: {global_err}")
                def create_global_failure():
                    TestResult.objects.create(
                        test_run=test_run,
                        step_number=1 if total_steps == 0 else total_steps,
                        status='FAILED',
                        error=f"Playwright Execution Crash: {str(global_err)}"
                    )
                    task_record.status = 'failed'
                    task_record.error = f"Execution Crash: {str(global_err)}"
                    task_record.completed_at = timezone.now()
                    task_record.save()
                run_in_thread(create_global_failure)

        # Save overall metrics and update task progress in a thread
        def complete_test_run(run_failed_local, passed_steps_local, total_steps_local):
            test_run.status = 'FAILED' if run_failed_local else 'COMPLETED'
            test_run.metadata = {
                "passed_steps": passed_steps_local,
                "total_steps": total_steps_local,
                "api_calls": api_logs
            }
            test_run.save()

            task_record.status = 'success'
            task_record.progress = 100
            task_record.result = {
                "status_text": f"Test run finished with status: {test_run.status}. Passed {passed_steps_local}/{total_steps_local} steps.",
                "passed_steps": passed_steps_local,
                "total_steps": total_steps_local
            }
            task_record.completed_at = timezone.now()
            task_record.save()
        run_in_thread(complete_test_run, run_failed, passed_steps, total_steps)

        # Trigger Bug Detection task asynchronously
        from tasks.bug_detection import detect_bugs
        detect_bugs.delay(test_run.id)
        
    except Exception as e:
        logger.error(f"Failed to execute test run task: {e}")
        def handle_run_error():
            task_record.status = 'failed'
            task_record.error = str(e)
            task_record.completed_at = timezone.now()
            task_record.save()
        run_in_thread(handle_run_error)
        return {"error": f"Failed to execute test: {str(e)}"}

    return {
        "status": test_run.status,
        "passed_steps": passed_steps,
        "total_steps": total_steps
    }
