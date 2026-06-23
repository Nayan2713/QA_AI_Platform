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
        app = run_in_thread(lambda: test_case.app)
        
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

        # Get previous successful run to extract baseline calls for schema regression checks
        prev_calls = []
        try:
            def get_prev_run_calls():
                prev_run = TestRun.objects.filter(
                    test_case=test_case,
                    status='COMPLETED'
                ).order_by('-created_at').first()
                if prev_run and isinstance(prev_run.metadata, dict):
                    return prev_run.metadata.get('api_calls', [])
                return []
            prev_calls = run_in_thread(get_prev_run_calls)
        except Exception as prev_err:
            logger.error(f"Error fetching baseline run: {prev_err}")

        with sync_playwright() as p:
            try:
                # Launch browser
                browser = p.chromium.launch(headless=True)
                
                # Fetch storage state
                def get_storage():
                    return app.storage_state
                storage_state = run_in_thread(get_storage)
                
                import json
                context_kwargs = {
                    "viewport": {"width": 1280, "height": 720},
                    "ignore_https_errors": True
                }
                if storage_state:
                    try:
                        context_kwargs["storage_state"] = json.loads(storage_state)
                        logger.info("Loaded pre-existing storage state for execution context.")
                    except Exception as e:
                        logger.error(f"Failed parsing storage state: {e}")
                
                context = browser.new_context(**context_kwargs)
                page = context.new_page()
                
                # Register background API response listener (registered BEFORE login/navigation)
                request_timestamps = {}

                def capture_network_request(request):
                    try:
                        if request.resource_type in ['xhr', 'fetch']:
                            import time
                            request_timestamps[request.url] = time.time()
                    except Exception:
                        pass

                page.on("request", capture_network_request)

                def capture_network_api(response):
                    try:
                        resource_type = response.request.resource_type
                        if resource_type in ['xhr', 'fetch']:
                            import time
                            start_time = request_timestamps.get(response.url)
                            latency = int((time.time() - start_time) * 1000) if start_time else 0

                            body_text = ""
                            try:
                                content_type = response.headers.get("content-type", "").lower()
                                if any(t in content_type for t in ["json", "text", "javascript", "xml"]):
                                    body_text = response.text()
                            except Exception:
                                pass

                            api_logs.append({
                                "method": response.request.method,
                                "url": response.url,
                                "status": response.status,
                                "body": body_text,
                                "latency": latency
                            })
                    except Exception as net_err:
                        logger.error(f"Error logging network response: {net_err}")

                page.on("response", capture_network_api)
                
                # Perform login if app has login credentials
                if app.login_url and app.username and app.password:
                    already_logged_in = False
                    if storage_state:
                        try:
                            logger.info("Verifying if existing session is valid for execution...")
                            page.goto(app.url, wait_until="load", timeout=10000)
                            page.wait_for_timeout(1000)
                            
                            if page.url.split('?')[0].rstrip('/') != app.login_url.split('?')[0].rstrip('/'):
                                still_has_password = False
                                password_selectors = ["input[type='password']", "input[name='password']", "input[id='password']"]
                                for sel in password_selectors:
                                    try:
                                        if page.locator(sel).first.is_visible():
                                            still_has_password = True
                                            break
                                    except Exception:
                                        continue
                                if not still_has_password:
                                    already_logged_in = True
                                    logger.info("Already logged in for execution. Skipping login step.")
                        except Exception as check_err:
                            logger.warning(f"Error checking session validity: {check_err}")
                            
                    if not already_logged_in:
                        logger.info(f"Executing pre-run login for app {app.url} at {app.login_url}")
                        try:
                            page.goto(app.login_url, wait_until="load", timeout=15000)
                            try:
                                page.wait_for_load_state("networkidle", timeout=3000)
                            except Exception:
                                pass
                            
                            # Username fields
                            username_selectors = [
                                "input[name='username']", "input[name='email']", "input[id='username']", 
                                "input[id='email']", "input[type='email']", "input[type='text']"
                            ]
                            # Password fields
                            password_selectors = [
                                "input[type='password']", "input[name='password']", "input[id='password']"
                            ]
                            # Submit buttons
                            submit_selectors = [
                                "button[type='submit']", "input[type='submit']", "button:has-text('Login')", 
                                "button:has-text('Sign In')", "button:has-text('Log In')"
                            ]

                            user_el = None
                            for sel in username_selectors:
                                try:
                                    if page.locator(sel).first.is_visible():
                                        user_el = page.locator(sel).first
                                        break
                                except Exception:
                                    continue

                            pass_el = None
                            for sel in password_selectors:
                                try:
                                    if page.locator(sel).first.is_visible():
                                        pass_el = page.locator(sel).first
                                        break
                                except Exception:
                                    continue

                            if user_el and pass_el:
                                user_el.fill(app.username)
                                pass_el.fill(app.password)
                                
                                submitted = False
                                for sel in submit_selectors:
                                    try:
                                        if page.locator(sel).first.is_visible():
                                            page.locator(sel).first.click()
                                            submitted = True
                                            break
                                    except Exception:
                                        continue
                                if not submitted:
                                    pass_el.press("Enter")
                                page.wait_for_timeout(3000)
                                
                                # Verify if login was successful, and save storage state if so
                                still_has_password = False
                                for sel in password_selectors:
                                    try:
                                        if page.locator(sel).first.is_visible():
                                            still_has_password = True
                                            break
                                    except Exception:
                                        continue
                                        
                                if not still_has_password:
                                    new_state = context.storage_state()
                                    def save_new_storage():
                                        app.storage_state = json.dumps(new_state)
                                        app.save()
                                    run_in_thread(save_new_storage)
                                    logger.info("Pre-run login completed successfully and storage state saved.")
                                else:
                                    logger.warning("Pre-run login completed, but password field still visible.")
                                    def save_heuristic_fail():
                                        app.login_status = 'FAILED'
                                        app.login_error = f"Pre-run login failed heuristic: stayed on URL '{page.url}' and password input field remained visible."
                                        app.save()
                                    run_in_thread(save_heuristic_fail)
                            else:
                                logger.warning("Pre-run login fields not found.")
                                def save_fields_missing():
                                    app.login_status = 'FAILED'
                                    app.login_error = "Pre-run login failed: could not locate standard email/username and password input fields on page."
                                    app.save()
                                run_in_thread(save_fields_missing)
                        except Exception as login_err:
                            logger.error(f"Pre-run login failed: {login_err}")
                            def save_login_exception():
                                app.login_status = 'FAILED'
                                app.login_error = f"Pre-run login exception: {str(login_err)}"
                                app.save()
                            run_in_thread(save_login_exception)
                
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
                    
                    max_attempts = 2
                    for attempt in range(max_attempts):
                        step_passed = True
                        error_msg = None
                        try:
                            if action == "navigate":
                                if not target:
                                    raise ValueError("Navigation action requires a target URL")
                                page.goto(target, wait_until="load")
                                # Wait for network to stabilize
                                try:
                                    page.wait_for_load_state("networkidle", timeout=3000)
                                except Exception:
                                    pass  # Networkidle timeout is non-fatal for navigation
                                
                            elif action == "fill":
                                if not selector:
                                    raise ValueError("Fill action requires a selector")
                                # Ensure visibility before filling
                                page.locator(selector).first.wait_for(state="visible", timeout=4000)
                                page.locator(selector).first.fill(value)
                                
                            elif action == "click":
                                if not selector:
                                    raise ValueError("Click action requires a selector")
                                page.locator(selector).first.wait_for(state="visible", timeout=4000)
                                page.locator(selector).first.click()
                                # Brief wait to let transitions or state updates settle
                                page.wait_for_timeout(500)
                                
                            elif action == "wait":
                                wait_ms = int(value) if value.isdigit() else 1000
                                page.wait_for_timeout(wait_ms)
                                
                            elif action == "assert":
                                # If a selector is provided, look in it. Otherwise look in the entire body.
                                if selector:
                                    page.locator(selector).first.wait_for(state="visible", timeout=4000)
                                    content = page.locator(selector).first.inner_text()
                                else:
                                    content = page.locator("body").inner_text()
                                    
                                if value.lower() not in content.lower():
                                    raise AssertionError(f"Assertion failed: Expected '{value}' to be present, but found: '{content[:120]}...'")
                            
                            elif action == "hover":
                                if not selector:
                                    raise ValueError("Hover action requires a selector")
                                page.locator(selector).first.wait_for(state="visible", timeout=4000)
                                page.locator(selector).first.hover()
                                page.wait_for_timeout(200)
                                
                            elif action == "scroll":
                                # Scroll down by pixel value or scroll an element into view
                                if selector:
                                    page.locator(selector).first.scroll_into_view_if_needed()
                                else:
                                    scroll_y = int(value) if value.isdigit() else 500
                                    page.evaluate(f"window.scrollBy(0, {scroll_y})")
                                page.wait_for_timeout(500)
                                
                            elif action == "select":
                                if not selector:
                                    raise ValueError("Select action requires a selector")
                                page.locator(selector).first.wait_for(state="visible", timeout=4000)
                                page.locator(selector).first.select_option(value)
                                page.wait_for_timeout(200)
                                
                            elif action == "screenshot":
                                try:
                                    screenshot_bytes = page.screenshot(type="png", full_page=False)
                                    screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                                except Exception as screenshot_err:
                                    logger.error(f"Failed to capture manual screenshot: {screenshot_err}")
                            
                            else:
                                raise ValueError(f"Unknown action type: {action}")
                                
                            # Step succeeded, break out of retry loop
                            break
                            
                        except Exception as e:
                            step_passed = False
                            error_msg = str(e)
                            if attempt < max_attempts - 1:
                                logger.warning(f"Step {step_num} failed on attempt {attempt + 1}. Retrying in 1.5s... Error: {error_msg}")
                                page.wait_for_timeout(1500)
                            else:
                                run_failed = True
                                logger.error(f"Step {step_num} failed final attempt: {error_msg}")
                                
                                # Capture screenshot on final failure
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

                # Inspect background API logs for response quality warnings/errors
                try:
                    from services.quality_analyzer import ResponseQualityAnalyzer
                    quality_issues = ResponseQualityAnalyzer.analyze_response_quality(api_logs, prev_calls, expected_result=test_case.expected_result, base_url=test_case.app.url)
                    # Filter out latency warnings from being fatal errors (they are performance warnings)
                    fatal_quality_issues = [q for q in quality_issues if q['type'] in ['content_error', 'schema_regression', 'semantic_error']]
                    
                    if fatal_quality_issues:
                        run_failed = True
                        quality_details = "\n".join([
                            f"- {q['method']} {q['url']}\n  Issue [{q['type'].upper()}]: {q['issue']}"
                            for q in fatal_quality_issues
                        ])
                        def log_quality_failures():
                            TestResult.objects.create(
                                test_run=test_run,
                                step_number=total_steps + 1,
                                status='FAILED',
                                error=f"API Response Quality Failures Detected:\n{quality_details}"
                            )
                        run_in_thread(log_quality_failures)
                        total_steps += 1
                except Exception as qual_err:
                    logger.error(f"Error executing response quality analyzer: {qual_err}")

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
