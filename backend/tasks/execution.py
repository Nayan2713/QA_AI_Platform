import logging
import base64
import threading
import json
import os
import time
from django.conf import settings
from django.utils import timezone
from celery import shared_task
from django.db import transaction
from playwright.sync_api import sync_playwright, Browser, BrowserContext

from core.models import TestRun, TestResult, TestCase, CeleryTask
from tasks.cancellation import check_cancelled, is_cancelled, clear_stop_flag, TaskCancelled, register_active_handle, unregister_active_handle
from services.self_healing_service import SelfHealingService
from services.image_compressor import ImageCompressor

logger = logging.getLogger(__name__)

_local_pool = threading.local()

def get_shared_browser() -> Browser:
    # If the thread doesn't have a browser, or it was disconnected, launch it
    playwright = getattr(_local_pool, "playwright", None)
    browser = getattr(_local_pool, "browser", None)
    
    if playwright is None or browser is None or not browser.is_connected():
        if playwright:
            try:
                playwright.stop()
            except Exception:
                pass
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-default-apps",
                "--disable-sync",
                "--disable-translate",
                "--metrics-recording-only",
                "--mute-audio",
                "--no-first-run",
            ]
        )
        _local_pool.playwright = playwright
        _local_pool.browser = browser
        logger.info(f"Thread-local browser instance created for thread: {threading.current_thread().name}")
    return browser


def close_thread_browser():
    """Safely stop thread-local Playwright browser instance if active."""
    playwright = getattr(_local_pool, "playwright", None)
    browser = getattr(_local_pool, "browser", None)
    if browser:
        try:
            browser.close()
        except Exception:
            pass
    if playwright:
        try:
            playwright.stop()
        except Exception:
            pass
    _local_pool.browser = None
    _local_pool.playwright = None


# ─────────────────────────────────────────────────────────────
# FIX 2: Session cache — store validated session state per app
#         in memory so the "is session still valid?" check
#         (which costs a full page.goto) only runs ONCE per
#         worker lifetime, not once per test.
# ─────────────────────────────────────────────────────────────
_session_cache: dict[int, dict] = {}  # app_id → {storage_state, validated_at}
_session_lock = threading.Lock()
SESSION_TTL = 3600  # re-validate session after 1 hour

def get_cached_session(app_id: int):
    with _session_lock:
        entry = _session_cache.get(app_id)
        if entry and (time.time() - entry["validated_at"]) < SESSION_TTL:
            return entry["storage_state"]
    return None

def set_cached_session(app_id: int, storage_state: dict):
    with _session_lock:
        _session_cache[app_id] = {
            "storage_state": storage_state,
            "validated_at": time.time()
        }

def invalidate_session_cache(app_id: int):
    with _session_lock:
        _session_cache.pop(app_id, None)


os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

from django.db import close_old_connections

def run_in_thread(func, *args, **kwargs):
    """
    Directly executes the function and ensures obsolete or stale
    database connections are cleaned up.
    """
    try:
        return func(*args, **kwargs)
    finally:
        close_old_connections()



def perform_login(page, context, app) -> bool:
    """
    Shared login helper. Returns True on success.
    """
    try:
        page.goto(app.login_url, wait_until="domcontentloaded", timeout=20000)
        # Don't wait for networkidle here — just proceed when DOM is ready
    except Exception as e:
        logger.warning(f"Navigation to login page issue: {e}")

    username_selectors = [
        "input[name='username']", "input[name='email']",
        "input[id='username']", "input[id='email']",
        "input[type='email']", "input[type='text']"
    ]
    password_selectors = [
        "input[type='password']", "input[name='password']", "input[id='password']"
    ]
    submit_selectors = [
        "button[type='submit']", "input[type='submit']",
        "button:has-text('Login')", "button:has-text('Sign In')", "button:has-text('Log In')"
    ]

    user_el = next(
        (page.locator(s).first for s in username_selectors
         if _is_visible(page, s)), None
    )
    pass_el = next(
        (page.locator(s).first for s in password_selectors
         if _is_visible(page, s)), None
    )

    if not (user_el and pass_el):
        logger.warning("Login fields not found.")
        return False

    user_el.fill(app.username)
    pass_el.fill(app.password)

    submitted = False
    for sel in submit_selectors:
        if _is_visible(page, sel):
            page.locator(sel).first.click()
            submitted = True
            break
    if not submitted:
        pass_el.press("Enter")

    # ─── FIX 3: Replace fixed 3000ms sleep with smart wait ───
    # Wait until the password field disappears (login succeeded)
    # or timeout after 5s — whichever comes first.
    try:
        page.wait_for_selector(
            "input[type='password']",
            state="hidden",
            timeout=5000
        )
    except Exception:
        pass  # Field may have never been there — check below

    still_has_password = any(_is_visible(page, s) for s in password_selectors)
    if still_has_password:
        logger.warning("Login failed: password field still visible after submit.")
        return False

    new_state = context.storage_state()
    set_cached_session(app.id, new_state)

    def persist_storage():
        app.storage_state = json.dumps(new_state)
        app.login_status = 'SUCCESS'
        app.save()
    run_in_thread(persist_storage)
    logger.info("Login successful, session cached.")
    return True


def _is_visible(page, selector: str) -> bool:
    try:
        return page.locator(selector).first.is_visible()
    except Exception:
        return False


def ensure_authenticated(page, context, app) -> bool:
    if not (app.login_url and app.username and app.password):
        return True
    is_on_login = page.url.split('?')[0].rstrip('/') == app.login_url.split('?')[0].rstrip('/')
    has_password = any(_is_visible(page, s) for s in [
        "input[type='password']", "input[name='password']", "input[id='password']"
    ])
    if is_on_login or has_password:
        logger.info("Session lost — re-authenticating...")
        invalidate_session_cache(app.id)
        return perform_login(page, context, app)
    return True



@shared_task(bind=True, name="tasks.execution.execute_test", queue="execution")
def execute_test(self, test_run_id, model_choice=None):

    logger.info(f"Starting test execution task for TestRun ID: {test_run_id} with model_choice: {model_choice}")
    task_id = self.request.id or "dummy_task_id"

    # ─── Immediate Cancellation Check ───
    if is_cancelled(task_id):
        logger.info(f"[CANCELLATION] Task {task_id} already cancelled before start.")
        def _cancel_task_record():
            CeleryTask.objects.filter(task_id=task_id).update(status='failed', error='Task stopped by user.')
            TestRun.objects.filter(id=test_run_id).update(status='FAILED')
        run_in_thread(_cancel_task_record)
        clear_stop_flag(task_id)
        return {"status": "CANCELLED", "message": "Stopped by user."}

    def get_or_create_task():
        obj, created = CeleryTask.objects.get_or_create(
            task_id=task_id,
            defaults={
                'task_type': 'execution',
                'status': 'progress',
                'progress': 10,
                'result': {"status_text": "Starting test execution..."}
            }
        )
        if not created:
            obj.status = 'progress'
            obj.progress = 10
            obj.result = {"status_text": "Starting test execution..."}
            obj.save()
        return obj

    task_record = run_in_thread(get_or_create_task)

    try:
        try:
            # OPTIMIZED: load test_case and app in a single DB query
            test_run = run_in_thread(
                lambda: TestRun.objects.select_related('test_case__app').get(id=test_run_id)
            )
        except TestRun.DoesNotExist:
            logger.error(f"TestRun {test_run_id} does not exist.")
            return {"error": f"TestRun {test_run_id} not found."}

        test_case = test_run.test_case   # already prefetched
        app = test_case.app              # already prefetched

        # Check if cancelled while waiting in queue or marked FAILED
        if is_cancelled(task_id) or test_run.status == 'FAILED':
            logger.info(f"[CANCELLATION] TestRun {test_run_id} (task {task_id}) marked FAILED/Cancelled — aborting.")
            def _abort_run():
                task_record.status = 'failed'
                task_record.error = 'Task stopped by user.'
                task_record.save()
                test_run.status = 'FAILED'
                test_run.save(update_fields=['status'])
            run_in_thread(_abort_run)
            clear_stop_flag(task_id)
            return {"status": "CANCELLED", "message": "Stopped by user."}

        from services.test_classifier import TestClassifier
        engine = TestClassifier.classify_test_case(test_case)

        if engine == 'BROWSER_USE':
            return _run_browser_use_test(test_run, test_case, app, task_record, model_choice)

        # ─── Mark run as RUNNING and clear old results ───
        def init_test_run():
            if is_cancelled(task_id) or test_run.status == 'FAILED':
                raise TaskCancelled("Test run was stopped by user.")
            test_run.status = 'RUNNING'
            test_run.metadata = {"engine_used": "PLAYWRIGHT"}
            test_run.save()
            TestResult.objects.filter(test_run=test_run).delete()
        run_in_thread(init_test_run)

        steps = test_case.steps
        total_steps = len(steps)
        passed_steps = 0
        run_failed = False
        api_logs = []
        console_logs = []
        video_relative_path = None
        har_relative_path = None

        # ─────────────────────────────────────────────────────
        # FIX 1 (continued): Reuse shared browser; only create
        # a new context per test (isolated cookies/storage).
        # ─────────────────────────────────────────────────────
        browser = get_shared_browser()

        context_kwargs = {
            "viewport": {"width": 1280, "height": 720},
            "ignore_https_errors": True,
        }

        # ─── FIX 2 (continued): Use in-memory cached session ───
        cached_state = get_cached_session(app.id)
        if cached_state:
            context_kwargs["storage_state"] = cached_state
            logger.info("Using in-memory cached session state.")
        else:
            def get_storage():
                return app.storage_state
            raw_storage = run_in_thread(get_storage)
            if raw_storage:
                try:
                    parsed = json.loads(raw_storage)
                    context_kwargs["storage_state"] = parsed
                    set_cached_session(app.id, parsed)
                    cached_state = parsed
                    logger.info("Loaded storage state from DB and cached it.")
                except Exception as e:
                    logger.error(f"Failed parsing storage state: {e}")

        context: BrowserContext = browser.new_context(**context_kwargs)
        register_active_handle(task_id, context)

        # ─── FIX 4: Aggressive default timeouts ───
        # 15s was set previously — 3s is enough for most SPAs
        # and prevents long hangs on bad selectors.
        context.set_default_timeout(3000)
        context.set_default_navigation_timeout(20000)

        page = context.new_page()
        register_active_handle(task_id, page)

        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))

        request_timestamps = {}

        def capture_request(request):
            if request.resource_type in ('xhr', 'fetch'):
                request_timestamps[request.url] = time.time()

        def capture_response(response):
            try:
                if response.request.resource_type not in ('xhr', 'fetch'):
                    return
                start = request_timestamps.get(response.url)
                latency = int((time.time() - start) * 1000) if start else 0
                body_text = ""
                try:
                    ct = response.headers.get("content-type", "").lower()
                    if response.status >= 200 and response.status not in (204, 304) and any(t in ct for t in ("json", "text", "javascript", "xml")):
                        raw = response.body()
                        if raw[:2] == b'\x1f\x8b':
                            import gzip
                            try:
                                raw = gzip.decompress(raw)
                            except Exception:
                                pass
                        body_text = raw.decode('utf-8', errors='replace')
                        if body_text and len(body_text) > 2000:
                            body_text = body_text[:2000] + "\n...[TRUNCATED FOR DATABASE PERFORMANCE]..."
                except Exception:
                    pass
                api_logs.append({
                    "method": response.request.method,
                    "url": response.url,
                    "status": response.status,
                    "body": body_text,
                    "latency": latency
                })
            except Exception as e:
                logger.error(f"Network capture error: {e}")

        page.on("request", capture_request)
        page.on("response", capture_response)

        try:
            # ─── Login if needed ───────────────────────────
            if app.login_url and app.username and app.password:
                # ─── FIX 2: Only do the session-validity check
                #     if we have NO cached session. If we have
                #     a cached session, trust it and skip the
                #     extra page.goto(app.url) — saves 3–5s.
                if cached_state:
                    logger.info("Cached session present — skipping validity check, trusting session.")
                else:
                    logger.info("No cached session — performing login...")
                    perform_login(page, context, app)

            # ─────────────────────────────────────────────────
            # FIX 5: Batch the "browser initialized" DB write
            #         into the first real step's result save,
            #         instead of a standalone run_in_thread call.
            # ─────────────────────────────────────────────────
            pending_init_result = True  # will be flushed with first step

            # ─── Step execution loop ───────────────────────
            for index, step in enumerate(steps):
                # Cooperative cancellation: check stop flag before every step
                check_cancelled(task_id)

                ensure_authenticated(page, context, app)

                step_num = index + 1
                action = step.get("action", "")
                selector = step.get("selector", "")
                target = step.get("target", "")
                value = step.get("value", "")

                logger.info(
                    f"Running step {step_num}/{total_steps}: "
                    f"{action} | Selector: '{selector}' | Target: '{target}' | Value: '{value}'"
                )

                # ─── FIX 6: Update progress WITHOUT a thread
                #     for every single step — use a lightweight
                #     batch update instead.
                # ─────────────────────────────────────────────
                if step_num % 3 == 0 or step_num == total_steps:
                    def _update_progress(sn=step_num, ac=action, tg=target, sel=selector):
                        task_record.progress = int(10 + (sn / total_steps) * 80)
                        task_record.result = {
                            "status_text": f"Step {sn}/{total_steps}: {ac.upper()} {tg or sel}",
                            "step_number": sn,
                            "total_steps": total_steps
                        }
                        task_record.save()
                    run_in_thread(_update_progress)

                step_passed = True
                error_msg = None
                screenshot_b64 = None
                step_auto_healed = False
                step_healing_details = None

                for attempt in range(2):
                    step_passed = True
                    error_msg = None
                    try:
                        if action == "navigate":
                            if not target:
                                raise ValueError("Navigate requires target URL")
                            page.goto(target, wait_until="domcontentloaded")

                        elif action == "fill":
                            if not selector:
                                raise ValueError("Fill requires a selector")
                            page.locator(selector).first.wait_for(state="visible", timeout=2000)
                            page.locator(selector).first.fill(value)

                        elif action == "click":
                            if not selector:
                                raise ValueError("Click requires a selector")
                            loc = page.locator(selector).first
                            loc.wait_for(state="visible", timeout=2000)
                            try:
                                loc.click(timeout=2000)
                            except Exception:
                                try:
                                    loc.click(force=True, timeout=1500)
                                except Exception:
                                    loc.evaluate("el => el.click()")

                        elif action == "wait":
                            raw_ms = int(value) if str(value).isdigit() else 1000
                            page.wait_for_timeout(min(raw_ms, 800))

                        elif action == "assert":
                            safe_value = value.replace("\\", "\\\\").replace('"', '\\"')
                            if selector:
                                try:
                                    page.wait_for_selector(
                                        f'{selector}:has-text("{safe_value}")',
                                        timeout=2000,
                                        state="visible"
                                    )
                                except Exception:
                                    page.locator(selector).first.wait_for(state="visible", timeout=2000)
                                    content = page.locator(selector).first.inner_text()
                                    if value.lower() not in content.lower():
                                        raise AssertionError(
                                            f"Assertion failed: Expected '{value}' not found. "
                                            f"Found: '{content[:120]}...'"
                                        )
                            else:
                                try:
                                    page.get_by_text(value, exact=False).first.wait_for(
                                        timeout=2000, state="visible"
                                    )
                                except Exception:
                                    content = page.locator("body").inner_text()
                                    if value.lower() not in content.lower():
                                        raise AssertionError(
                                            f"Assertion failed: Expected '{value}' not found. "
                                            f"Found: '{content[:120]}...'"
                                        )

                        elif action == "hover":
                            if not selector:
                                raise ValueError("Hover requires a selector")
                            page.locator(selector).first.wait_for(state="visible", timeout=2000)
                            page.locator(selector).first.hover()

                        elif action == "scroll":
                            if selector:
                                page.locator(selector).first.scroll_into_view_if_needed()
                            else:
                                scroll_y = int(value) if str(value).isdigit() else 500
                                page.evaluate(f"window.scrollBy(0, {scroll_y})")

                        elif action == "select":
                            if not selector:
                                raise ValueError("Select requires a selector")
                            loc = page.locator(selector).first
                            loc.wait_for(state="visible", timeout=2000)
                            is_select = loc.evaluate("el => el.tagName.toLowerCase() === 'select'")
                            if is_select:
                                loc.select_option(value)
                            else:
                                try:
                                    loc.click(timeout=1500)
                                except Exception:
                                    loc.evaluate("el => el.click()")
                                page.wait_for_timeout(400)
                                option_clicked = False
                                for t_loc in [
                                    page.locator(f"text={value}"),
                                    page.locator(f"li:has-text('{value}')"),
                                    page.locator(f"span:has-text('{value}')"),
                                ]:
                                    try:
                                        for candidate in t_loc.all():
                                            if candidate.is_visible():
                                                candidate.click(timeout=1000)
                                                option_clicked = True
                                                break
                                        if option_clicked:
                                            break
                                    except Exception:
                                        continue
                                if not option_clicked:
                                    try:
                                        loc.fill(value)
                                        page.keyboard.press("Enter")
                                    except Exception as fe:
                                        logger.error(f"Dropdown fallback failed: {fe}")

                        elif action == "screenshot":
                            try:
                                raw_ss = page.screenshot(type="png", full_page=False)
                                raw_b64 = base64.b64encode(raw_ss).decode('utf-8')
                                screenshot_b64 = ImageCompressor.compress_base64(raw_b64, max_dim=1280, quality=75, format='WEBP')
                            except Exception as se:
                                logger.error(f"Manual screenshot failed: {se}")

                        else:
                            raise ValueError(f"Unknown action: {action}")

                        break  # success — exit retry loop

                    except TaskCancelled:
                        # Never treat a user stop as a step failure/retry.
                        raise
                    except Exception as e:
                        step_passed = False
                        error_msg = str(e)
                        
                        # ─── SELF-HEALING ENGINE ATTEMPT ───────────────
                        heal_res = SelfHealingService.heal_selector(page, step)
                        if heal_res.get("success"):
                            healed_sel = heal_res["healed_selector"]
                            logger.info(f"[EXECUTION SELF-HEALED] Step {step_num}: '{selector}' ➔ '{healed_sel}'")
                            try:
                                h_loc = page.locator(healed_sel).first
                                if action == "click":
                                    h_loc.click(timeout=8000)
                                elif action == "fill":
                                    h_loc.fill(str(value), timeout=8000)
                                elif action == "select":
                                    h_loc.select_option(str(value), timeout=8000)
                                elif action == "assert":
                                    if not h_loc.is_visible():
                                        raise AssertionError(f"Healed element '{healed_sel}' not visible.")

                                # Self-healing succeeded!
                                step_passed = True
                                step_auto_healed = True
                                step_healing_details = heal_res
                                error_msg = f"Self-Healed selector: '{selector}' ➔ '{healed_sel}' ({heal_res.get('reason', '')})"

                                # Persist healed selector back to TestCase
                                try:
                                    tc = test_run.test_case
                                    if tc and isinstance(tc.steps, list) and index < len(tc.steps):
                                        tc.steps[index]['selector'] = healed_sel
                                        tc.self_healed_count = (tc.self_healed_count or 0) + 1
                                        tc.save(update_fields=['steps', 'self_healed_count'])
                                    test_run.self_healed_count = (test_run.self_healed_count or 0) + 1
                                    test_run.save(update_fields=['self_healed_count'])
                                except Exception as save_h_err:
                                    logger.warning(f"Failed to persist self-healed step: {save_h_err}")

                                break  # exit retry loop with success!
                            except Exception as h_err:
                                logger.warning(f"[SELF-HEALING EXECUTION FAILED] Action failed on healed selector '{healed_sel}': {h_err}")

                        if attempt == 0:
                            logger.warning(
                                f"Step {step_num} failed attempt 1, retrying in 1s... {error_msg}"
                            )
                            check_cancelled(task_id)
                            page.wait_for_timeout(400)
                        else:
                            run_failed = True
                            logger.error(f"Step {step_num} final failure: {error_msg}")
                            try:
                                raw_ss = page.screenshot(type="png", full_page=False)
                                raw_b64 = base64.b64encode(raw_ss).decode('utf-8')
                                screenshot_b64 = ImageCompressor.compress_base64(raw_b64, max_dim=1280, quality=75, format='WEBP')
                            except Exception:
                                pass

                if step_passed:
                    passed_steps += 1

                # ─── FIX 5: Batch DB write — flush init result
                #     together with the first step result in a
                #     single transaction.
                # ─────────────────────────────────────────────
                def save_step(
                    sp=step_passed, em=error_msg, sc=screenshot_b64,
                    sn=step_num, ps=passed_steps, ts=total_steps,
                    al=list(api_logs), cl=list(console_logs),
                    ah=step_auto_healed, hd=step_healing_details,
                    flush_init=pending_init_result
                ):
                    with transaction.atomic():
                        if flush_init:
                            TestResult.objects.create(
                                test_run=test_run,
                                step_number=0,
                                status='PASSED',
                                error="Browser initialized."
                            )
                        TestResult.objects.create(
                            test_run=test_run,
                            step_number=sn,
                            status='PASSED' if sp else 'FAILED',
                            error=em,
                            screenshot=sc,
                            auto_healed=ah,
                            healing_details=hd
                        )
                        # I6 FIX: Update metadata in-memory then save,
                        # instead of the previous SELECT + UPDATE that
                        # was non-atomic and could lose concurrent writes.
                        test_run.metadata = {
                            **(test_run.metadata or {}),
                            "passed_steps": ps,
                            "total_steps": ts,
                            "api_calls": al,
                            "console_logs": cl,
                        }
                        test_run.save(update_fields=['metadata'])

                run_in_thread(save_step)
                pending_init_result = False

                if not step_passed:
                    logger.warning(f"Aborting at step {step_num}.")
                    break

            # ─── Post-execution: API error check ──────────
            failed_apis = [log for log in api_logs if log['status'] >= 400]
            if failed_apis:
                run_failed = True
                details = "\n".join(
                    f"- {l['method']} {l['url']} → {l['status']}"
                    for l in failed_apis
                )
                def log_api_failures():
                    TestResult.objects.create(
                        test_run=test_run,
                        step_number=total_steps + 1,
                        status='FAILED',
                        # error=f"API failures:\n{details}"
                        error=f"API Network Failures Detected:\n{details}"
                    )
                run_in_thread(log_api_failures)
                total_steps += 1



            # ─── Close context only, NOT the browser ─────────
            context.close()
            video_relative_path = None
            har_relative_path = None

        except TaskCancelled:
            # Propagate to the outer handler which marks the run CANCELLED.
            logger.info("Test execution cancelled by user — closing context.")
            try:
                context.close()
            except Exception:
                pass
            raise
        except Exception as global_err:
            run_failed = True
            logger.error(f"Playwright runner crash: {global_err}")
            try:
                context.close()
            except Exception:
                pass
            def save_crash():
                TestResult.objects.create(
                    test_run=test_run,
                    step_number=max(1, total_steps),
                    status='FAILED',
                    error=f"Playwright crash: {global_err}"
                )
                task_record.status = 'failed'
                task_record.error = str(global_err)
                task_record.completed_at = timezone.now()
                task_record.save()
                _check_batch_completion(app.id, task_id)
            run_in_thread(save_crash)
            return {"error": str(global_err)}

        # ─── Finalize test run ─────────────────────────────
        def complete_run():
            test_run.status = 'FAILED' if run_failed else 'COMPLETED'
            test_run.metadata = {
                "passed_steps": passed_steps,
                "total_steps": total_steps,
                "api_calls": api_logs,
                "console_logs": console_logs,
                "video_path": video_relative_path,
                "har_path": har_relative_path,
                "engine_used": "PLAYWRIGHT"
            }
            test_run.save()
            task_record.status = 'success'
            task_record.progress = 100
            task_record.result = {
                "status_text": f"Done: {test_run.status}. {passed_steps}/{total_steps} passed.",
                "passed_steps": passed_steps,
                "total_steps": total_steps
            }
            task_record.completed_at = timezone.now()
            task_record.save()
            _check_batch_completion(app.id, task_id)
        run_in_thread(complete_run)

        # Check captured api_calls latency against this app's
        # PerformanceThreshold and record any breaches as Bug rows
        # (bug_type='performance'). Never allowed to fail the test run.
        try:
            from services.performance_checker import check_performance_thresholds
            run_in_thread(lambda: check_performance_thresholds(test_run))
        except Exception as perf_err:
            logger.error(f"Performance threshold check failed: {perf_err}")

        # OPTIMIZED: pass only test_run_id — api_logs already stored in
        # TestRun.metadata, avoiding a potentially large broker payload.
        run_quality_analysis.apply_async(args=[test_run.id], queue='quality')

        # Auto-trigger visual regression after every completed UI test run
        from tasks.visual_and_api_tasks import run_visual_regression
        run_visual_regression.apply_async(args=[test_run.id], countdown=2)

    except TaskCancelled:
        logger.info(f"execute_test {task_id} cancelled by user.")
        def handle_cancelled():
            try:
                test_run.status = 'FAILED'
                test_run.save(update_fields=['status'])
            except Exception:
                pass
            task_record.status = 'failed'
            task_record.error = 'Stopped by user.'
            task_record.completed_at = timezone.now()
            task_record.save()
            clear_stop_flag(task_id)
            _check_batch_completion(app.id, task_id)
        run_in_thread(handle_cancelled)
        return {"status": "CANCELLED", "message": "Stopped by user."}

    except Exception as e:
        logger.error(f"execute_test outer failure: {e}")
        def handle_outer_error():
            task_record.status = 'failed'
            task_record.error = str(e)
            task_record.completed_at = timezone.now()
            task_record.save()
            clear_stop_flag(task_id)
            _check_batch_completion(app.id, task_id)
        run_in_thread(handle_outer_error)
        return {"error": str(e)}

    clear_stop_flag(task_id)

    return {
        "status": test_run.status,
        "passed_steps": passed_steps,
        "total_steps": total_steps
    }


def _check_batch_completion(app_id: int, completed_task_id: str):
    """
    Checks if a task belongs to an active batch_execution CeleryTask.
    Removes completed_task_id from pending_tasks, updates batch progress %, and if pending_tasks is empty,
    marks the parent batch_execution task as 'success' and progress 100%.
    """
    def _do_check():
        try:
            batch_tasks = CeleryTask.objects.filter(
                app_id=app_id,
                task_type='batch_execution',
                status__in=['pending', 'progress', 'running']
            )
            for b_task in batch_tasks:
                result_data = dict(b_task.result or {})
                pending = list(result_data.get('pending_tasks', []))
                
                # 1. Remove current completed task ID
                if completed_task_id in pending:
                    pending.remove(completed_task_id)

                # 2. Self-healing check: purge any task IDs from pending if their DB status is already finished
                if pending:
                    finished_ids = set(CeleryTask.objects.filter(
                        task_id__in=pending,
                        status__in=['success', 'failed', 'completed', 'cancelled', 'revoked']
                    ).values_list('task_id', flat=True))
                    if finished_ids:
                        pending = [tid for tid in pending if tid not in finished_ids]

                result_data['pending_tasks'] = pending
                batch_total = result_data.get('batch_total') or (len(pending) + result_data.get('completed_count', 0))
                completed_count = max(0, batch_total - len(pending))
                result_data['completed_count'] = completed_count
                
                if batch_total > 0:
                    b_task.progress = min(100, int((completed_count / batch_total) * 100))
                result_data['status_text'] = f"Executed {completed_count}/{batch_total} test case(s) in batch suite..."
                b_task.result = result_data

                if len(pending) == 0:
                    b_task.status = 'success'
                    b_task.progress = 100
                    b_task.completed_at = timezone.now()
                    result_data['status_text'] = f"Batch suite completed successfully ({batch_total} test case(s) executed)."
                    b_task.result = result_data
                
                b_task.save()
        except Exception as e:
            logger.error(f"Error checking batch completion: {e}")
    run_in_thread(_do_check)


def _run_browser_use_test(test_run, test_case, app, task_record, model_choice=None):
    """Extracted BROWSER_USE path — unchanged logic, just moved here."""
    from services.browser_use_agent import BrowserUseAgent
    from tasks.discovery import run_async

    def run_agentic():
        agent = BrowserUseAgent(model_choice=model_choice)
        credentials = {"username": app.username, "password": app.password} if app.username else None
        task_record.progress = 40
        task_record.result = {"status_text": "AI agent executing test case..."}
        task_record.save()
        return run_async(agent.generate_and_execute_test(test_case, app.url, credentials))

    agent_result = run_in_thread(run_agentic)
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
            TestResult.objects.create(
                test_run=test_run,
                step_number=1,
                status='PASSED' if status_val == 'COMPLETED' else 'FAILED',
                error=None if status_val == 'COMPLETED' else result_summary,
                screenshot=screenshot_path
            )
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
                "status_text": f"Agent done. Status: {status_val}",
                "passed_steps": 1 if status_val == 'COMPLETED' else 0,
                "total_steps": 1
            }
            task_record.completed_at = timezone.now()
            task_record.save()

    run_in_thread(save_agent_results)
    return {"status": "SUCCESS", "engine": "BROWSER_USE", "result": status_val}


@shared_task(name="tasks.execution.run_quality_analysis", queue="quality")
def run_quality_analysis(test_run_id, api_logs=None):
    """
    Async quality analysis task.

    OPTIMIZED: api_logs is now optional. When not supplied (new default),
    the task reads them from TestRun.metadata in the DB, avoiding a
    potentially multi-MB broker payload.
    """
    logger.info(f"Starting async quality analysis task for TestRun ID: {test_run_id}")

    def analyze():
        from core.models import TestRun, TestResult, APIEndpoint
        from services.quality_analyzer import ResponseQualityAnalyzer

        try:
            # OPTIMIZED: prefetch test_case and app in one query
            test_run = TestRun.objects.select_related('test_case__app').get(id=test_run_id)
        except TestRun.DoesNotExist:
            logger.error(f"TestRun {test_run_id} does not exist in run_quality_analysis.")
            return

        if test_run.status == 'FAILED' and (test_run.metadata or {}).get('stopped_by_user'):
            logger.info(f"Skipping quality analysis for user-cancelled TestRun ID {test_run_id}")
            return

        test_case = test_run.test_case
        app = test_case.app

        # OPTIMIZED: read api_logs from DB metadata if not passed directly
        nonlocal api_logs
        if api_logs is None:
            api_logs = (test_run.metadata or {}).get('api_calls', [])

        try:
            # Query prev_calls inside the async task
            prev = TestRun.objects.filter(
                test_case=test_case, status='COMPLETED'
            ).exclude(id=test_run_id).order_by('-created_at').first()
            prev_calls = prev.metadata.get('api_calls', []) if prev and isinstance(prev.metadata, dict) else []

            endpoints = {
                (ep.method, ep.url_pattern): ep
                for ep in APIEndpoint.objects.filter(application=app)
            }
            
            quality_issues = ResponseQualityAnalyzer.analyze_response_quality(
                api_logs, prev_calls,
                expected_result=test_case.expected_result,
                base_url=test_case.app.url,
                app=test_case.app,
                endpoints_cache=endpoints
            )
            
            fatal = [q for q in quality_issues if q['type'] in (
                'content_error', 'schema_regression',
                'semantic_error', 'schema_conformance'
            )]
            
            if fatal:
                details_list = []
                for q in fatal:
                    body_preview = ""
                    q_body = q.get('body')
                    if q_body:
                        body_preview = q_body[:600] + "\n  ... [TRUNCATED] ..." if len(q_body) > 600 else q_body
                        body_preview = body_preview.strip()
                    
                    details_list.append(
                        f"- {q['method']} {q['url']}\n"
                        f"  [{q['type'].upper()}]: {q['issue']}\n"
                        f"  Response Status: {q.get('status')} | Latency: {q.get('latency')}ms\n"
                        f"  Response Content:\n  {body_preview}" if body_preview else f"- {q['method']} {q['url']}\n  [{q['type'].upper()}]: {q['issue']}\n  Response Status: {q.get('status')} | Latency: {q.get('latency')}ms"
                    )
                details = "\n".join(details_list)
                
                total_steps = TestResult.objects.filter(test_run=test_run).count()
                
                with transaction.atomic():
                    TestResult.objects.create(
                        test_run=test_run,
                        step_number=total_steps + 1,
                        status='FAILED',
                        # error=f"Quality failures:\n{details}"
                        error=f"API Response Quality Failures Detected:\n{details}"
                    )
                    
                    test_run.status = 'FAILED'
                    test_run.save()
                    
            # Recalculate passed and total steps in metadata
            with transaction.atomic():
                tr = TestRun.objects.get(id=test_run.id)
                meta = tr.metadata or {}
                meta["passed_steps"] = TestResult.objects.filter(test_run=tr, status='PASSED').count()
                meta["total_steps"] = TestResult.objects.filter(test_run=tr).count()
                tr.metadata = meta
                tr.save()
                
        except Exception as qe:
            logger.error(f"Quality analyzer error for TestRun ID {test_run_id}: {qe}")
            
        finally:
            # Bug detection runs after the quality checks are finished (unless cancelled)
            if test_run and not (test_run.status == 'FAILED' and (test_run.metadata or {}).get('stopped_by_user')):
                from tasks.bug_detection import detect_bugs
                detect_bugs.apply_async(args=[test_run_id], queue='quality')

    run_in_thread(analyze)