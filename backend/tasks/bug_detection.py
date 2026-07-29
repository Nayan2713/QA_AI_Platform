import base64
import logging
import os
import re
import time
from urllib.parse import urlparse
from celery import shared_task
from django.conf import settings
from django.db import transaction

from core.models import TestRun, TestResult, Bug, APIEndpoint
from tasks.discovery import get_url_pattern
from tasks.cancellation import check_cancelled, clear_stop_flag, TaskCancelled

logger = logging.getLogger(__name__)


def save_screenshot_to_file(screenshot_b64, prefix="bug"):
    """
    Decodes a base64 screenshot string and saves it as a PNG file under
    MEDIA_ROOT/bugs/. Returns the relative path (e.g. 'bugs/bug_1234.png')
    suitable for storing in an ImageField, or None on failure.
    """
    if not screenshot_b64:
        return None
    try:
        media_path = os.path.join(settings.MEDIA_ROOT, 'bugs')
        os.makedirs(media_path, exist_ok=True)
        filename = f"{prefix}_{int(time.time() * 1000)}.png"
        filepath = os.path.join(media_path, filename)
        image_data = base64.b64decode(screenshot_b64)
        with open(filepath, 'wb') as f:
            f.write(image_data)
        return f"bugs/{filename}"
    except Exception as err:
        logger.error(f"Failed to save bug screenshot to file: {err}")
        return None

def classify_severity(error_message):
    """
    Classifies bug severity based on keywords present in the error message.
    - critical: crash, error, timeout, 500, exception, failed to load, network failure
    - high: invalid, not found, unexpected, wrong, assertion, regression, schema regression, quality failure
    - medium: missing, slow, layout, display, visible
    - low: typo, spacing, color
    """
    err = error_message.lower()
    
    critical_kws = [
        'crash', 'exception', 'traceback', 'internal server error',
        '500', '502', '503', 'failed to load', 'not reachable',
        'network failure', 'database error', 'sql error',
    ]
    if any(kw in err for kw in critical_kws):
        return 'critical'

    # High: functional / data correctness failures.
    high_kws = [
        'invalid', 'not found', '404', 'unexpected', 'assertion failed',
        'schema regression', 'schema conformance', 'quality failure',
        'success=false', '401', '403',
    ]
    if any(kw in err for kw in high_kws):
        return 'high'

    # Medium: UI / rendering / content issues.
    # 'visible' and 'wait_for' removed — they collide with normal
    # Playwright "waiting for element to be visible" prose.
    medium_kws = ['missing field', 'slow', 'high response latency', 'layout', 'display']
    if any(kw in err for kw in medium_kws):
        return 'medium'

    # Low: cosmetic.
    low_kws = ['typo', 'spacing', 'color']
    if any(kw in err for kw in low_kws):
        return 'low'

    return 'medium'
    # # Critical keywords
    # critical_kws = ['crash', 'error', 'timeout', '500', 'exception', 'failed to load', 'not reachable', 'network failures']
    # if any(kw in err for kw in critical_kws):
    #     return 'critical'
        
    # # High keywords
    # high_kws = ['invalid', 'not found', 'unexpected', 'wrong', 'assertion', 'regression', 'schema regression', 'quality failures']
    # if any(kw in err for kw in high_kws):
    #     return 'high'
        
    # # Medium keywords
    # medium_kws = ['missing', 'slow', 'layout', 'display', 'visible', 'wait_for']
    # if any(kw in err for kw in medium_kws):
    #     return 'medium'
        
    # # Low keywords
    # low_kws = ['typo', 'spacing', 'color']
    # if any(kw in err for kw in low_kws):
    #     return 'low'
        
    # return 'medium'


@shared_task(name="tasks.bug_detection.detect_bugs")
def detect_bugs(test_run_id):
    """
    Celery task that analyzes test results for a TestRun,
    identifies failures, classifies them by severity, and creates bug records.
    """
    logger.info(f"Starting bug detection task for TestRun ID: {test_run_id}")
    
    try:
        test_run = TestRun.objects.get(id=test_run_id)
    except TestRun.DoesNotExist:
        logger.error(f"TestRun with ID {test_run_id} does not exist.")
        return {"error": f"TestRun with ID {test_run_id} not found."}

    if test_run.status == 'FAILED' and (test_run.metadata or {}).get('stopped_by_user'):
        logger.info(f"Skipping bug detection for user-cancelled TestRun ID {test_run_id}")
        return {"status": "SKIPPED_CANCELLED", "bugs_found": 0}

    # Fetch failed results
    failed_results = TestResult.objects.filter(test_run=test_run, status='FAILED')
    
    bugs_created = 0
    
    try:
        with transaction.atomic():
            # Clear previous bugs for this test case to avoid duplicates across runs
            #Bug.objects.filter(test_run__test_case=test_run.test_case).delete()
            Bug.objects.filter(test_run=test_run).delete()

            
            seen_bugs_in_run = set()
            for result in failed_results:
                error_msg = result.error or "Unknown error occurred"
                
                # Exclude test automation harness/script issues from being logged as application bugs
                test_harness_keywords = [
                    'syntaxerror', 'not a valid selector', 'waiting for locator',
                    'playwright execution crash', 'timeout exceeded', 'strict mode violation',
                    'locator.click: timeout', 'locator.fill: timeout'
                ]
                err_msg_lower = error_msg.lower()
                if any(kw in err_msg_lower for kw in test_harness_keywords):
                    logger.info(f"Skipping application bug ticket creation for test-harness/selector error: {error_msg[:120]}...")
                    continue
                
                step_num = result.step_number
                
                # Fetch step information if possible
                steps = test_run.test_case.steps
                step_details = {}
                if len(steps) >= step_num:
                    step_details = steps[step_num - 1]
                
                action = step_details.get("action", "unknown")
                selector = step_details.get("selector", "")
                target = step_details.get("target", "")
                value = step_details.get("value", "")
                
                # Classify severity
                severity = classify_severity(error_msg)
                
                # Build bug info
                title = f"Step {step_num} Failed: '{action.upper()}' action issue"
                
                # Check for virtual API steps to set more descriptive titles/descriptions
                is_virtual_api_step = False
                if "API Network Failures Detected" in error_msg:
                    action = "api network"
                    title = "API Network Failures Detected"
                    is_virtual_api_step = True
                elif "API Response Quality Failures Detected" in error_msg:
                    action = "api response quality"
                    title = "API Response Quality Failures Detected"
                    is_virtual_api_step = True

                details_parts = []
                if selector: details_parts.append(f"selector '{selector}'")
                if target: details_parts.append(f"target '{target}'")
                if value: details_parts.append(f"value '{value}'")
                details_str = ", ".join(details_parts)
                
                if is_virtual_api_step:
                    description = (
                        f"An automated quality assertion check failed for background API requests during the test run.\n"
                        f"Validation details:\n{error_msg}"
                    )
                else:
                    description = (
                        f"During the execution of test step {step_num} doing '{action}', an error occurred.\n"
                        f"Action details: {details_str if details_str else 'none'}\n"
                        f"Error output:\n{error_msg}"
                    )
                
                matched_endpoint = None
                if is_virtual_api_step:
                    lines = error_msg.split('\n')
                    for line in lines:
                        match = re.search(r'-\s+([A-Z]+)\s+([^\s]+)\s+->\s+Status\s+(\d+)', line)
                        if not match:
                            # Try to match latency/schema warnings e.g. "- GET http://example.com/api/users"
                            match = re.search(r'-\s+([A-Z]+)\s+([^\s]+)', line)
                            
                        if match:
                            method = match.group(1).strip()
                            url = match.group(2).strip()
                            
                            # Normalize URL to match pattern
                            url_pattern = get_url_pattern(url, test_run.test_case.app.url)
                            
                            matched_endpoint = APIEndpoint.objects.filter(
                                application=test_run.test_case.app,
                                method=method,
                                url_pattern=url_pattern
                            ).first()
                            if matched_endpoint:
                                break
                                
                # Deduplicate bugs within the same test run using a signature
                norm_title = re.sub(r'Step \d+ Failed', 'Step Failed', title)
                endpoint_id = matched_endpoint.id if matched_endpoint else 0
                run_key = (norm_title, endpoint_id, severity)
                
                if run_key in seen_bugs_in_run:
                    logger.info(f"Skipping duplicate bug ticket within the same run: {title}")
                    continue
                seen_bugs_in_run.add(run_key)
                
                # Create Bug
                # TestResult.screenshot stores raw base64 — decode & save to a file
                # so the Bug ImageField gets a proper relative path.
                step_screenshot = save_screenshot_to_file(
                    result.screenshot, prefix=f"bug_run{test_run_id}_step{step_num}"
                ) if result.screenshot and result.screenshot != 'None' else None
                Bug.objects.create(
                    application=test_run.test_case.app,
                    test_run=test_run,
                    title=title,
                    description=description,
                    severity=severity,
                    api_endpoint=matched_endpoint,
                    screenshot=step_screenshot
                )
                bugs_created += 1
                
            # Update bugs count on TestRun
            test_run.bugs_found = bugs_created
            test_run.save()
            
            logger.info(f"Detected and created {bugs_created} bug records.")
            
    except Exception as e:
        logger.error(f"Failed to process bug records: {e}")
        return {"error": f"Failed to detect bugs: {str(e)}"}

    return {
        "status": "SUCCESS",
        "bugs_found": bugs_created
    }


@shared_task(bind=True, name="tasks.bug_detection.start_agentic_bug_detection")
def start_agentic_bug_detection(self, app_id):
    """
    Celery task that triggers autonomous browser-use agent execution
    to audit the entire application context and generate bug reports.
    """
    logger.info(f"Starting agentic bug detection task for application ID: {app_id}")
    task_id = self.request.id or "dummy_task_id"
    
    from core.models import CeleryTask, Application
    from tasks.discovery import run_async, run_in_thread
    from django.utils import timezone
    
    def get_or_create_task():
        obj, created = CeleryTask.objects.get_or_create(
            task_id=task_id,
            defaults={
                'task_type': 'bug_detection',
                'status': 'progress',
                'progress': 10,
                'result': {"status_text": "Starting agentic bug audit..."}
            }
        )
        if not created:
            obj.status = 'progress'
            obj.progress = 10
            obj.result = {"status_text": "Starting agentic bug audit..."}
            obj.save()
        return obj

    task_record = run_in_thread(get_or_create_task)
    
    try:
        app = run_in_thread(Application.objects.get, id=app_id)
    except Application.DoesNotExist:
        logger.error(f"Application with ID {app_id} does not exist.")
        def handle_missing_app():
            task_record.status = 'failed'
            task_record.error = f"Application with ID {app_id} not found."
            task_record.completed_at = timezone.now()
            task_record.save()
        run_in_thread(handle_missing_app)
        return {"error": f"Application with ID {app_id} not found."}

    try:
        # Cooperative cancellation before the expensive agentic browser run
        check_cancelled(task_id)

        from services.browser_use_agent import BrowserUseAgent

        def run_agentic_bugs():
            agent = BrowserUseAgent()
            credentials = {
                "username": app.username,
                "password": app.password
            } if app.username else None
            
            task_record.progress = 45
            task_record.result = {"status_text": "AI agent actively auditing subpages and forms for defects..."}
            task_record.save()
            
            return run_async(agent.detect_bugs(app, credentials))
            
        bugs_found = run_in_thread(run_agentic_bugs)

        # Cancellation may have been requested while the agent was running.
        check_cancelled(task_id)

        def save_bugs():
            with transaction.atomic():
                # OPTIMIZED: bulk_create instead of one INSERT per bug.
                Bug.objects.bulk_create([
                    Bug(
                        application=app,
                        bug_type=b_info.get("bug_type", "functional"),
                        severity=b_info.get("severity", "medium"),
                        title=b_info.get("title", "Discovered UI/Functional Bug"),
                        description=b_info.get("description", "Error observed during crawler audit."),
                        element_selector=b_info.get("element_selector"),
                        screenshot=b_info.get("screenshot"),
                        status="open"
                    )
                    for b_info in bugs_found
                ], batch_size=100)
                
                task_record.status = 'success'
                task_record.progress = 100
                task_record.result = {
                    "bugs_found": len(bugs_found),
                    "status_text": f"Agent finished audit. Discovered {len(bugs_found)} bug tickets."
                }
                task_record.completed_at = timezone.now()
                task_record.save()
                
        run_in_thread(save_bugs)
        clear_stop_flag(task_id)
        return {"status": "SUCCESS", "bugs_found": len(bugs_found)}

    except TaskCancelled:
        logger.info(f"Agentic bug detection task {task_id} cancelled by user.")
        def handle_bug_cancelled():
            try:
                task_record.status = 'failed'
                task_record.error = 'Stopped by user.'
                task_record.completed_at = timezone.now()
                task_record.save()
            finally:
                clear_stop_flag(task_id)
        run_in_thread(handle_bug_cancelled)
        return {"status": "CANCELLED", "message": "Bug detection stopped by user."}

    except Exception as e:
        logger.error(f"Agentic bug detection failed: {e}")
        def handle_error():
            try:
                task_record.status = 'failed'
                task_record.error = str(e)
                task_record.completed_at = timezone.now()
                task_record.save()
            finally:
                clear_stop_flag(task_id)
        run_in_thread(handle_error)
        return {"status": "FAILED", "error": str(e)}


def run_in_thread(func, *args, **kwargs):
    return func(*args, **kwargs)


@shared_task(bind=True)
def scan_ui_bugs(self, app_id):
    """
    Celery task to run automated UI/visual defect scanner on an application.
    """
    from core.models import Application, CeleryTask
    from services.ui_scanner import run_ui_scan
    from tasks.cancellation import check_cancelled, clear_stop_flag, TaskCancelled
    
    logger.info(f"Starting UI bug scan task for application ID: {app_id}")
    task_id = self.request.id or "dummy_task_id"
    
    def get_app():
        return Application.objects.get(id=app_id)
        
    def update_task(status_str, bugs_count, err=None):
        t = CeleryTask.objects.filter(task_id=task_id).first()
        if t:
            t.status = status_str
            t.progress = 100 if status_str == 'success' else 0
            if err:
                t.error = str(err)
            else:
                t.result = {"bugs_found": bugs_count, "status_text": f"UI scan complete. Found {bugs_count} visual defects."}
            t.save()
            
    try:
        check_cancelled(task_id)
        app = run_in_thread(get_app)
        bugs = run_ui_scan(app, task_id=task_id)
        check_cancelled(task_id)
        run_in_thread(lambda: update_task('success', len(bugs)))
        clear_stop_flag(task_id)
        return {"status": "SUCCESS", "ui_bugs_found": len(bugs)}
    except TaskCancelled:
        logger.info(f"UI bug scan task {task_id} cancelled by user.")
        run_in_thread(lambda: update_task('failed', 0, err='Stopped by user.'))
        clear_stop_flag(task_id)
        return {"status": "CANCELLED", "message": "UI bug scan stopped by user."}
    except Exception as e:
        logger.error(f"UI bug scan task failed: {e}")
        run_in_thread(lambda: update_task('failed', 0, err=e))
        clear_stop_flag(task_id)
        return {"status": "FAILED", "error": str(e)}