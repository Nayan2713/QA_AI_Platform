import logging
import base64
import threading
import json
import os
from django.conf import settings
from django.utils import timezone
from celery import shared_task
from django.db import transaction
from playwright.sync_api import sync_playwright

from core.models import TestRun, TestResult, TestCase, CeleryTask

logger = logging.getLogger(__name__)

def ensure_authenticated(page, context, app):
    if not (app.login_url and app.username and app.password):
        return True
    
    # Check if we are currently on the login URL or if a password field is visible
    is_login_url = page.url.split('?')[0].rstrip('/') == app.login_url.split('?')[0].rstrip('/')
    password_selectors = ["input[type='password']", "input[name='password']", "input[id='password']"]
    has_password_field = False
    for sel in password_selectors:
        try:
            if page.locator(sel).first.is_visible():
                has_password_field = True
                break
        except Exception:
            continue
            
    if is_login_url or has_password_field:
        logger.info(f"Session lost or on login page. Performing auto re-authentication for {app.url}...")
        try:
            if is_login_url:
                page.goto(app.login_url, wait_until="domcontentloaded", timeout=15000)
            
            # Find elements and log in
            username_selectors = ["input[name='username']", "input[name='email']", "input[id='username']", "input[id='email']", "input[type='email']", "input[type='text']"]
            submit_selectors = ["button[type='submit']", "input[type='submit']", "button:has-text('Login')", "button:has-text('Sign In')", "button:has-text('Log In')"]
            
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
                
                # Check success
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
                        app.login_status = 'SUCCESS'
                        app.save()
                    run_in_thread(save_new_storage)
                    logger.info("Auto re-authentication completed successfully.")
                    return True
        except Exception as e:
            logger.error(f"Auto re-authentication failed: {e}")
            return False
    return True


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
            # FIX: append a tuple so None return values don't leave res empty,
            # which previously caused IndexError on res[0] for save()/delete() calls.
            res.append((func(*args, **kwargs),))
        except Exception as e:
            err.append(e)
        finally:
            connection.close()

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    if err:
        raise err[0]
    # res[0] is a 1-tuple; unwrap it. Returns None when func returned None.
    return res[0][0] if res else None

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
        
        from services.test_classifier import TestClassifier
        engine = TestClassifier.classify_test_case(test_case)
        
        if engine == 'BROWSER_USE':
            logger.info(f"Executing test run {test_run_id} via BROWSER-USE Agent...")
            from services.browser_use_agent import BrowserUseAgent
            from tasks.discovery import run_async
            
            def run_agentic_test():
                agent = BrowserUseAgent()
                credentials = {
                    "username": app.username,
                    "password": app.password
                } if app.username else None
                
                task_record.progress = 40
                task_record.result = {"status_text": "AI agent executing test case dynamically..."}
                task_record.save()
                
                return run_async(agent.generate_and_execute_test(test_case, app.url, credentials))
                
            agent_result = run_in_thread(run_agentic_test)
            status_val = agent_result.get("status")
            result_summary = agent_result.get("result")
            screenshot_path = agent_result.get("screenshot_path")
            bug_details = agent_result.get("bug_details")
            
            def save_agent_results():
                with transaction.atomic():
                    test_run.status = 'COMPLETED' if status_val == 'COMPLETED' else 'FAILED'
                    test_run.metadata = {
                        "engine_used": "BROWSER_USE",
                        "summary": result_summary,
                        "screenshot_path": screenshot_path
                    }
                    test_run.save()
                    
                    # Create a single summary TestResult step
                    TestResult.objects.create(
                        test_run=test_run,
                        step_number=1,
                        status='PASSED' if status_val == 'COMPLETED' else 'FAILED',
                        error=None if status_val == 'COMPLETED' else result_summary,
                        screenshot=screenshot_path
                    )
                    
                    # If failed, log bug ticket
                    if bug_details:
                        from core.models import Bug
                        Bug.objects.create(
                            application=app,
                            test_run=test_run,
                            bug_type=bug_details.get("bug_type", "functional"),
                            severity=bug_details.get("severity", "medium"),
                            title=bug_details.get("title", "AI Agent Failure"),
                            description=bug_details.get("description", "Agent failed to verify expected result."),
                            screenshot=screenshot_path
                        )
                        test_run.bugs_found = 1
                        test_run.save()
                        
                    task_record.status = 'success'
                    task_record.progress = 100
                    task_record.result = {
                        "status_text": f"Agent finished. Status: {status_val}",
                        "passed_steps": 1 if status_val == 'COMPLETED' else 0,
                        "total_steps": 1
                    }
                    task_record.completed_at = timezone.now()
                    task_record.save()
                    
            run_in_thread(save_agent_results)
            return {"status": "SUCCESS", "engine": "BROWSER_USE", "result": status_val}

        def init_test_run():
            test_run.status = 'RUNNING'
            test_run.metadata = {"engine_used": "PLAYWRIGHT"}
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
                import os
                
                # Configure video capture
                video_dir = os.path.join(settings.MEDIA_ROOT, 'videos')
                os.makedirs(video_dir, exist_ok=True)
                
                # Configure HAR capture
                har_dir = os.path.join(settings.MEDIA_ROOT, 'har')
                os.makedirs(har_dir, exist_ok=True)
                har_file_path = os.path.join(har_dir, f"run_{test_run.id}.har")
                
                context_kwargs = {
                    "viewport": {"width": 1280, "height": 720},
                    "ignore_https_errors": True,
                    "record_video_dir": video_dir,
                    "record_har_path": har_file_path,
                    "record_har_mode": "minimal"
                }
                if storage_state:
                    try:
                        context_kwargs["storage_state"] = json.loads(storage_state)
                        logger.info("Loaded pre-existing storage state for execution context.")
                    except Exception as e:
                        logger.error(f"Failed parsing storage state: {e}")
                
                context = browser.new_context(**context_kwargs)
                page = context.new_page()
                
                # Listen to console messages
                console_logs = []
                page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
                
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
                                    raw_bytes = response.body()
                                    if raw_bytes.startswith(b'\x1f\x8b'):
                                        import gzip
                                        try:
                                            raw_bytes = gzip.decompress(raw_bytes)
                                        except Exception:
                                            pass
                                    body_text = raw_bytes.decode('utf-8', errors='replace')
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
                            page.goto(app.url, wait_until="domcontentloaded", timeout=15000)
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
                            try:
                                page.goto(app.login_url, wait_until="domcontentloaded", timeout=20000)
                                try:
                                    page.wait_for_load_state("networkidle", timeout=3000)
                                except Exception:
                                    pass
                            except Exception as goto_err:
                                logger.warning(f"Navigation to login page had an issue/timeout: {goto_err}. Trying to proceed anyway...")
                            
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
                
                # Log browser initialized checkpoint
                def log_browser_initialized():
                    TestResult.objects.create(
                        test_run=test_run,
                        step_number=0,
                        status='PASSED',
                        error="Browser environment initialized. Executing actions..."
                    )
                run_in_thread(log_browser_initialized)

                # Set default timeout to 15 seconds to allow slower websites to load
                page.set_default_timeout(15000)
                
                for index, step in enumerate(steps):
                    # Ensure the browser is still authenticated before executing the step
                    ensure_authenticated(page, context, app)

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
                                try:
                                    page.goto(target, wait_until="domcontentloaded")
                                    # Wait for network to stabilize
                                    try:
                                        page.wait_for_load_state("networkidle", timeout=3000)
                                    except Exception:
                                        pass  # Networkidle timeout is non-fatal for navigation
                                except Exception as e:
                                    raise Exception(f"Navigation to {target} failed: {e}")
                                
                            elif action == "fill":
                                if not selector:
                                    raise ValueError("Fill action requires a selector")
                                # Ensure visibility before filling
                                page.locator(selector).first.wait_for(state="visible", timeout=4000)
                                page.locator(selector).first.fill(value)
                                
                            elif action == "click":
                                if not selector:
                                    raise ValueError("Click action requires a selector")
                                locator = page.locator(selector).first
                                locator.wait_for(state="visible", timeout=4000)
                                try:
                                    locator.click(timeout=3000)
                                except Exception as click_err:
                                    logger.warning(f"Standard click failed on {selector}: {click_err}. Trying force click...")
                                    try:
                                        locator.click(force=True, timeout=2000)
                                    except Exception as force_err:
                                        logger.warning(f"Force click failed on {selector}: {force_err}. Falling back to JS click...")
                                        locator.evaluate("el => el.click()")
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
                                locator = page.locator(selector).first
                                locator.wait_for(state="visible", timeout=4000)
                                
                                # Check if it is a standard HTML select element
                                is_select = locator.evaluate("el => el.tagName.toLowerCase() === 'select'")
                                if is_select:
                                    locator.select_option(value)
                                else:
                                    # Custom dropdown handler
                                    logger.info(f"Custom select dropdown detected for selector '{selector}'. Expanding dropdown...")
                                    try:
                                        locator.click(timeout=2000)
                                    except Exception:
                                        locator.evaluate("el => el.click()")
                                    page.wait_for_timeout(600)
                                    
                                    option_clicked = False
                                    text_locators = [
                                        page.locator(f"text={value}"),
                                        page.locator(f"p:has-text('{value}')"),
                                        page.locator(f"span:has-text('{value}')"),
                                        page.locator(f"div:has-text('{value}')"),
                                        page.locator(f"li:has-text('{value}')")
                                    ]
                                    for t_loc in text_locators:
                                        try:
                                            candidates = t_loc.all()
                                            for candidate in candidates:
                                                if candidate.is_visible():
                                                    candidate.click(timeout=1500)
                                                    option_clicked = True
                                                    break
                                            if option_clicked:
                                                break
                                        except Exception:
                                            continue
                                            
                                    if not option_clicked:
                                        try:
                                            val_loc = page.locator(f"[value='{value}']")
                                            if val_loc.first.is_visible():
                                                val_loc.first.click(timeout=1500)
                                                option_clicked = True
                                        except Exception:
                                            pass
                                            
                                    if not option_clicked:
                                        logger.warning(f"Could not find clickable option for custom dropdown '{value}'. Attempting keyboard input fallback...")
                                        try:
                                            locator.fill(value)
                                            page.wait_for_timeout(400)
                                            page.keyboard.press("Enter")
                                            option_clicked = True
                                        except Exception as fill_err:
                                            logger.error(f"Keyboard input fallback failed: {fill_err}")
                                            
                                page.wait_for_timeout(300)
                                
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
                    
                    # Save step result and update metadata incrementally in a thread
                    def save_incremental_results(step_passed_local, error_msg_local, screenshot_b64_local, passed_local, total_local, api_logs_local, console_logs_local):
                        TestResult.objects.create(
                            test_run=test_run,
                            step_number=step_num,
                            status='PASSED' if step_passed_local else 'FAILED',
                            error=error_msg_local,
                            screenshot=screenshot_b64_local
                        )
                        # Fetch the latest test_run instance from DB to avoid overriding final status
                        tr = TestRun.objects.get(id=test_run.id)
                        meta = tr.metadata or {}
                        meta["passed_steps"] = passed_local
                        meta["total_steps"] = total_local
                        meta["api_calls"] = api_logs_local
                        meta["console_logs"] = console_logs_local
                        tr.metadata = meta
                        tr.save()
                        
                    run_in_thread(
                        save_incremental_results, 
                        step_passed, 
                        error_msg, 
                        screenshot_b64, 
                        passed_steps, 
                        total_steps, 
                        list(api_logs), 
                        list(console_logs)
                    )
                    
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
                    def run_quality_analysis():
                        return ResponseQualityAnalyzer.analyze_response_quality(
                            api_logs, 
                            prev_calls, 
                            expected_result=test_case.expected_result, 
                            base_url=test_case.app.url, 
                            app=test_case.app
                        )
                    quality_issues = run_in_thread(run_quality_analysis)
                    # Filter out latency warnings from being fatal errors (they are performance warnings)
                    fatal_quality_issues = [q for q in quality_issues if q['type'] in ['content_error', 'schema_regression', 'semantic_error', 'schema_conformance']]
                    
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

                video_full_path = None
                try:
                    if page.video:
                        video_full_path = page.video.path()
                except Exception:
                    pass

                context.close()
                browser.close()
                
                video_relative_path = None
                if video_full_path and os.path.exists(video_full_path):
                    video_relative_path = f"videos/{os.path.basename(video_full_path)}"
                
                har_relative_path = f"har/run_{test_run.id}.har"
                
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
                "api_calls": api_logs,
                "console_logs": console_logs if 'console_logs' in locals() or 'console_logs' in globals() else [],
                "video_path": video_relative_path if 'video_relative_path' in locals() else None,
                "har_path": har_relative_path if 'har_relative_path' in locals() else None
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


# import logging
# import base64
# import threading
# from django.utils import timezone
# from celery import shared_task
# from django.db import transaction
# from playwright.sync_api import sync_playwright

# from core.models import TestRun, TestResult, TestCase, CeleryTask

# logger = logging.getLogger(__name__)

# def run_in_thread(func, *args, **kwargs):
#     """
#     Runs a function inside a separate thread to bypass Django's SynchronousOnlyOperation check.
#     Closes the thread's DB connection afterwards to prevent connection leaks.
#     """
#     res = []
#     err = []
#     def target():
#         from django.db import connection
#         try:
#             res.append(func(*args, **kwargs))
#         except Exception as e:
#             err.append(e)
#         finally:
#             connection.close()
            
#     thread = threading.Thread(target=target)
#     thread.start()
#     thread.join()
#     if err:
#         raise err[0]
#     return res[0]

# @shared_task(bind=True, name="tasks.execution.execute_test")
# def execute_test(self, test_run_id):
#     """
#     Celery task that executes a TestCase step-by-step using Playwright,
#     tracking task progress in the CeleryTask registry.
#     """
#     logger.info(f"Starting test execution task for TestRun ID: {test_run_id}")
    
#     # Create/update task tracking record (runs in celery thread before Playwright is started)
#     task_id = self.request.id or "dummy_task_id"
    
#     def get_or_create_task():
#         obj, created = CeleryTask.objects.get_or_create(
#             task_id=task_id,
#             defaults={
#                 'task_type': 'execution',
#                 'status': 'progress',
#                 'progress': 10,
#                 'result': {"status_text": "Starting test execution run..."}
#             }
#         )
#         if not created:
#             obj.status = 'progress'
#             obj.progress = 10
#             obj.result = {"status_text": "Starting test execution run..."}
#             obj.save()
#         return obj

#     task_record = run_in_thread(get_or_create_task)
    
#     try:
#         try:
#             test_run = run_in_thread(TestRun.objects.get, id=test_run_id)
#         except TestRun.DoesNotExist:
#             logger.error(f"TestRun with ID {test_run_id} does not exist.")
#             def handle_missing_run():
#                 task_record.status = 'failed'
#                 task_record.error = f"TestRun with ID {test_run_id} not found."
#                 task_record.completed_at = timezone.now()
#                 task_record.save()
#             run_in_thread(handle_missing_run)
#             return {"error": f"TestRun with ID {test_run_id} not found."}

#         test_case = run_in_thread(lambda: test_run.test_case)
#         app = run_in_thread(lambda: test_case.app)
        
#         def init_test_run():
#             test_run.status = 'RUNNING'
#             test_run.save()
#             # Clear previous results
#             TestResult.objects.filter(test_run=test_run).delete()
#         run_in_thread(init_test_run)

#         steps = test_case.steps
#         total_steps = len(steps)
#         passed_steps = 0
#         run_failed = False
#         api_logs = []

#         # Get previous successful run to extract baseline calls for schema regression checks
#         prev_calls = []
#         try:
#             def get_prev_run_calls():
#                 prev_run = TestRun.objects.filter(
#                     test_case=test_case,
#                     status='COMPLETED'
#                 ).order_by('-created_at').first()
#                 if prev_run and isinstance(prev_run.metadata, dict):
#                     return prev_run.metadata.get('api_calls', [])
#                 return []
#             prev_calls = run_in_thread(get_prev_run_calls)
#         except Exception as prev_err:
#             logger.error(f"Error fetching baseline run: {prev_err}")

#         with sync_playwright() as p:
#             try:
#                 # Launch browser
#                 browser = p.chromium.launch(headless=True)
                
#                 # Fetch storage state
#                 def get_storage():
#                     return app.storage_state
#                 storage_state = run_in_thread(get_storage)
                
#                 import json
#                 context_kwargs = {
#                     "viewport": {"width": 1280, "height": 720},
#                     "ignore_https_errors": True
#                 }
#                 if storage_state:
#                     try:
#                         context_kwargs["storage_state"] = json.loads(storage_state)
#                         logger.info("Loaded pre-existing storage state for execution context.")
#                     except Exception as e:
#                         logger.error(f"Failed parsing storage state: {e}")
                
#                 context = browser.new_context(**context_kwargs)
#                 page = context.new_page()
                
#                 # Register background API response listener (registered BEFORE login/navigation)
#                 request_timestamps = {}

#                 def capture_network_request(request):
#                     try:
#                         if request.resource_type in ['xhr', 'fetch']:
#                             import time
#                             request_timestamps[request.url] = time.time()
#                     except Exception:
#                         pass

#                 page.on("request", capture_network_request)

#                 def capture_network_api(response):
#                     try:
#                         resource_type = response.request.resource_type
#                         if resource_type in ['xhr', 'fetch']:
#                             import time
#                             start_time = request_timestamps.get(response.url)
#                             latency = int((time.time() - start_time) * 1000) if start_time else 0

#                             body_text = ""
#                             try:
#                                 content_type = response.headers.get("content-type", "").lower()
#                                 if any(t in content_type for t in ["json", "text", "javascript", "xml"]):
#                                     body_text = response.text()
#                             except Exception:
#                                 pass

#                             api_logs.append({
#                                 "method": response.request.method,
#                                 "url": response.url,
#                                 "status": response.status,
#                                 "body": body_text,
#                                 "latency": latency
#                             })
#                     except Exception as net_err:
#                         logger.error(f"Error logging network response: {net_err}")

#                 page.on("response", capture_network_api)
                
#                 # Perform login if app has login credentials
#                 if app.login_url and app.username and app.password:
#                     already_logged_in = False
#                     if storage_state:
#                         try:
#                             logger.info("Verifying if existing session is valid for execution...")
#                             page.goto(app.url, wait_until="domcontentloaded", timeout=15000)
#                             page.wait_for_timeout(1000)
                            
#                             if page.url.split('?')[0].rstrip('/') != app.login_url.split('?')[0].rstrip('/'):
#                                 still_has_password = False
#                                 password_selectors = ["input[type='password']", "input[name='password']", "input[id='password']"]
#                                 for sel in password_selectors:
#                                     try:
#                                         if page.locator(sel).first.is_visible():
#                                             still_has_password = True
#                                             break
#                                     except Exception:
#                                         continue
#                                 if not still_has_password:
#                                     already_logged_in = True
#                                     logger.info("Already logged in for execution. Skipping login step.")
#                         except Exception as check_err:
#                             logger.warning(f"Error checking session validity: {check_err}")
                            
#                     if not already_logged_in:
#                         logger.info(f"Executing pre-run login for app {app.url} at {app.login_url}")
#                         try:
#                             try:
#                                 page.goto(app.login_url, wait_until="domcontentloaded", timeout=20000)
#                                 try:
#                                     page.wait_for_load_state("networkidle", timeout=3000)
#                                 except Exception:
#                                     pass
#                             except Exception as goto_err:
#                                 logger.warning(f"Navigation to login page had an issue/timeout: {goto_err}. Trying to proceed anyway...")
                            
#                             # Username fields
#                             username_selectors = [
#                                 "input[name='username']", "input[name='email']", "input[id='username']", 
#                                 "input[id='email']", "input[type='email']", "input[type='text']"
#                             ]
#                             # Password fields
#                             password_selectors = [
#                                 "input[type='password']", "input[name='password']", "input[id='password']"
#                             ]
#                             # Submit buttons
#                             submit_selectors = [
#                                 "button[type='submit']", "input[type='submit']", "button:has-text('Login')", 
#                                 "button:has-text('Sign In')", "button:has-text('Log In')"
#                             ]

#                             user_el = None
#                             for sel in username_selectors:
#                                 try:
#                                     if page.locator(sel).first.is_visible():
#                                         user_el = page.locator(sel).first
#                                         break
#                                 except Exception:
#                                     continue

#                             pass_el = None
#                             for sel in password_selectors:
#                                 try:
#                                     if page.locator(sel).first.is_visible():
#                                         pass_el = page.locator(sel).first
#                                         break
#                                 except Exception:
#                                     continue

#                             if user_el and pass_el:
#                                 user_el.fill(app.username)
#                                 pass_el.fill(app.password)
                                
#                                 submitted = False
#                                 for sel in submit_selectors:
#                                     try:
#                                         if page.locator(sel).first.is_visible():
#                                             page.locator(sel).first.click()
#                                             submitted = True
#                                             break
#                                     except Exception:
#                                         continue
#                                 if not submitted:
#                                     pass_el.press("Enter")
#                                 page.wait_for_timeout(3000)
                                
#                                 # Verify if login was successful, and save storage state if so
#                                 still_has_password = False
#                                 for sel in password_selectors:
#                                     try:
#                                         if page.locator(sel).first.is_visible():
#                                             still_has_password = True
#                                             break
#                                     except Exception:
#                                         continue
                                        
#                                 if not still_has_password:
#                                     new_state = context.storage_state()
#                                     def save_new_storage():
#                                         app.storage_state = json.dumps(new_state)
#                                         app.save()
#                                     run_in_thread(save_new_storage)
#                                     logger.info("Pre-run login completed successfully and storage state saved.")
#                                 else:
#                                     logger.warning("Pre-run login completed, but password field still visible.")
#                                     def save_heuristic_fail():
#                                         app.login_status = 'FAILED'
#                                         app.login_error = f"Pre-run login failed heuristic: stayed on URL '{page.url}' and password input field remained visible."
#                                         app.save()
#                                     run_in_thread(save_heuristic_fail)
#                             else:
#                                 logger.warning("Pre-run login fields not found.")
#                                 def save_fields_missing():
#                                     app.login_status = 'FAILED'
#                                     app.login_error = "Pre-run login failed: could not locate standard email/username and password input fields on page."
#                                     app.save()
#                                 run_in_thread(save_fields_missing)
#                         except Exception as login_err:
#                             logger.error(f"Pre-run login failed: {login_err}")
#                             def save_login_exception():
#                                 app.login_status = 'FAILED'
#                                 app.login_error = f"Pre-run login exception: {str(login_err)}"
#                                 app.save()
#                             run_in_thread(save_login_exception)
                
#                 # Set default timeout to 15 seconds to allow slower websites to load
#                 page.set_default_timeout(15000)
                
#                 for index, step in enumerate(steps):
#                     step_num = index + 1
#                     action = step.get("action")
#                     selector = step.get("selector", "")
#                     target = step.get("target", "")
#                     value = step.get("value", "")
                    
#                     logger.info(f"Running step {step_num}/{total_steps}: {action} | Selector: '{selector}' | Target: '{target}' | Value: '{value}'")
                    
#                     # Update progress in a thread
#                     def update_step_progress():
#                         task_record.progress = int(10 + (step_num / total_steps) * 80)
#                         details = f"target '{target}'" if action == "navigate" else f"selector '{selector}'"
#                         task_record.result = {
#                             "status_text": f"Running step {step_num}/{total_steps}: {action.upper()} {details}",
#                             "step_number": step_num,
#                             "total_steps": total_steps
#                         }
#                         task_record.save()
#                     run_in_thread(update_step_progress)

#                     step_passed = True
#                     error_msg = None
#                     screenshot_b64 = None
                    
#                     max_attempts = 2
#                     for attempt in range(max_attempts):
#                         step_passed = True
#                         error_msg = None
#                         try:
#                             if action == "navigate":
#                                 if not target:
#                                     raise ValueError("Navigation action requires a target URL")
#                                 try:
#                                     page.goto(target, wait_until="domcontentloaded")
#                                     # Wait for network to stabilize
#                                     try:
#                                         page.wait_for_load_state("networkidle", timeout=3000)
#                                     except Exception:
#                                         pass  # Networkidle timeout is non-fatal for navigation
#                                 except Exception as e:
#                                     raise Exception(f"Navigation to {target} failed: {e}")
                                
#                             elif action == "fill":
#                                 if not selector:
#                                     raise ValueError("Fill action requires a selector")
#                                 # Ensure visibility before filling
#                                 page.locator(selector).first.wait_for(state="visible", timeout=4000)
#                                 page.locator(selector).first.fill(value)
                                
#                             elif action == "click":
#                                 if not selector:
#                                     raise ValueError("Click action requires a selector")
#                                 page.locator(selector).first.wait_for(state="visible", timeout=4000)
#                                 page.locator(selector).first.click()
#                                 # Brief wait to let transitions or state updates settle
#                                 page.wait_for_timeout(500)
                                
#                             elif action == "wait":
#                                 wait_ms = int(value) if value.isdigit() else 1000
#                                 page.wait_for_timeout(wait_ms)
                                
#                             elif action == "assert":
#                                 # If a selector is provided, look in it. Otherwise look in the entire body.
#                                 if selector:
#                                     page.locator(selector).first.wait_for(state="visible", timeout=4000)
#                                     content = page.locator(selector).first.inner_text()
#                                 else:
#                                     content = page.locator("body").inner_text()
                                    
#                                 if value.lower() not in content.lower():
#                                     raise AssertionError(f"Assertion failed: Expected '{value}' to be present, but found: '{content[:120]}...'")
                            
#                             elif action == "hover":
#                                 if not selector:
#                                     raise ValueError("Hover action requires a selector")
#                                 page.locator(selector).first.wait_for(state="visible", timeout=4000)
#                                 page.locator(selector).first.hover()
#                                 page.wait_for_timeout(200)
                                
#                             elif action == "scroll":
#                                 # Scroll down by pixel value or scroll an element into view
#                                 if selector:
#                                     page.locator(selector).first.scroll_into_view_if_needed()
#                                 else:
#                                     scroll_y = int(value) if value.isdigit() else 500
#                                     page.evaluate(f"window.scrollBy(0, {scroll_y})")
#                                 page.wait_for_timeout(500)
                                
#                             elif action == "select":
#                                 if not selector:
#                                     raise ValueError("Select action requires a selector")
#                                 page.locator(selector).first.wait_for(state="visible", timeout=4000)
#                                 page.locator(selector).first.select_option(value)
#                                 page.wait_for_timeout(200)
                                
#                             elif action == "screenshot":
#                                 try:
#                                     screenshot_bytes = page.screenshot(type="png", full_page=False)
#                                     screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
#                                 except Exception as screenshot_err:
#                                     logger.error(f"Failed to capture manual screenshot: {screenshot_err}")
                            
#                             else:
#                                 raise ValueError(f"Unknown action type: {action}")
                                
#                             # Step succeeded, break out of retry loop
#                             break
                            
#                         except Exception as e:
#                             step_passed = False
#                             error_msg = str(e)
#                             if attempt < max_attempts - 1:
#                                 logger.warning(f"Step {step_num} failed on attempt {attempt + 1}. Retrying in 1.5s... Error: {error_msg}")
#                                 page.wait_for_timeout(1500)
#                             else:
#                                 run_failed = True
#                                 logger.error(f"Step {step_num} failed final attempt: {error_msg}")
                                
#                                 # Capture screenshot on final failure
#                                 try:
#                                     screenshot_bytes = page.screenshot(type="png", full_page=False)
#                                     screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
#                                 except Exception as screenshot_err:
#                                     logger.error(f"Failed to capture screenshot: {screenshot_err}")
                    
#                     if step_passed:
#                         passed_steps += 1
                    
#                     # Save step result in a thread
#                     def create_step_result(step_passed_local, error_msg_local, screenshot_b64_local):
#                         TestResult.objects.create(
#                             test_run=test_run,
#                             step_number=step_num,
#                             status='PASSED' if step_passed_local else 'FAILED',
#                             error=error_msg_local,
#                             screenshot=screenshot_b64_local
#                         )
#                     run_in_thread(create_step_result, step_passed, error_msg, screenshot_b64)
                    
#                     if not step_passed:
#                         logger.warning(f"Aborting execution at step {step_num} due to failure.")
#                         break
                    
#                 # Inspect background API log calls for status code errors (status >= 400)
#                 failed_apis = [log for log in api_logs if log['status'] >= 400]
#                 if failed_apis:
#                     run_failed = True
#                     error_details = "\n".join([
#                         f"- {log['method']} {log['url']} -> Status {log['status']}"
#                         for log in failed_apis
#                     ])
#                     def log_api_failures():
#                         TestResult.objects.create(
#                             test_run=test_run,
#                             step_number=total_steps + 1,
#                             status='FAILED',
#                             error=f"API Network Failures Detected:\n{error_details}"
#                         )
#                     run_in_thread(log_api_failures)
#                     total_steps += 1

#                 # Inspect background API logs for response quality warnings/errors
#                 try:
#                     from services.quality_analyzer import ResponseQualityAnalyzer
#                     quality_issues = ResponseQualityAnalyzer.analyze_response_quality(api_logs, prev_calls, expected_result=test_case.expected_result, base_url=test_case.app.url, app=test_case.app)
#                     # Filter out latency warnings from being fatal errors (they are performance warnings)
#                     fatal_quality_issues = [q for q in quality_issues if q['type'] in ['content_error', 'schema_regression', 'semantic_error', 'schema_conformance']]
                    
#                     if fatal_quality_issues:
#                         run_failed = True
#                         quality_details = "\n".join([
#                             f"- {q['method']} {q['url']}\n  Issue [{q['type'].upper()}]: {q['issue']}"
#                             for q in fatal_quality_issues
#                         ])
#                         def log_quality_failures():
#                             TestResult.objects.create(
#                                 test_run=test_run,
#                                 step_number=total_steps + 1,
#                                 status='FAILED',
#                                 error=f"API Response Quality Failures Detected:\n{quality_details}"
#                             )
#                         run_in_thread(log_quality_failures)
#                         total_steps += 1
#                 except Exception as qual_err:
#                     logger.error(f"Error executing response quality analyzer: {qual_err}")

#                 browser.close()
                
#             except Exception as global_err:
#                 run_failed = True
#                 logger.error(f"Global Playwright runner error: {global_err}")
#                 def create_global_failure():
#                     TestResult.objects.create(
#                         test_run=test_run,
#                         step_number=1 if total_steps == 0 else total_steps,
#                         status='FAILED',
#                         error=f"Playwright Execution Crash: {str(global_err)}"
#                     )
#                     task_record.status = 'failed'
#                     task_record.error = f"Execution Crash: {str(global_err)}"
#                     task_record.completed_at = timezone.now()
#                     task_record.save()
#                 run_in_thread(create_global_failure)

#         # Save overall metrics and update task progress in a thread
#         def complete_test_run(run_failed_local, passed_steps_local, total_steps_local):
#             test_run.status = 'FAILED' if run_failed_local else 'COMPLETED'
#             test_run.metadata = {
#                 "passed_steps": passed_steps_local,
#                 "total_steps": total_steps_local,
#                 "api_calls": api_logs
#             }
#             test_run.save()

#             task_record.status = 'success'
#             task_record.progress = 100
#             task_record.result = {
#                 "status_text": f"Test run finished with status: {test_run.status}. Passed {passed_steps_local}/{total_steps_local} steps.",
#                 "passed_steps": passed_steps_local,
#                 "total_steps": total_steps_local
#             }
#             task_record.completed_at = timezone.now()
#             task_record.save()
#         run_in_thread(complete_test_run, run_failed, passed_steps, total_steps)

#         # Trigger Bug Detection task asynchronously
#         from tasks.bug_detection import detect_bugs
#         detect_bugs.delay(test_run.id)
        
#     except Exception as e:
#         logger.error(f"Failed to execute test run task: {e}")
#         def handle_run_error():
#             task_record.status = 'failed'
#             task_record.error = str(e)
#             task_record.completed_at = timezone.now()
#             task_record.save()
#         run_in_thread(handle_run_error)
#         return {"error": f"Failed to execute test: {str(e)}"}

#     return {
#         "status": test_run.status,
#         "passed_steps": passed_steps,
#         "total_steps": total_steps
#     }
