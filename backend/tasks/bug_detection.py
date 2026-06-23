import logging
import re
from urllib.parse import urlparse
from celery import shared_task
from django.db import transaction

from core.models import TestRun, TestResult, Bug, APIEndpoint
from tasks.discovery import get_url_pattern

logger = logging.getLogger(__name__)

def classify_severity(error_message):
    """
    Classifies bug severity based on keywords present in the error message.
    - critical: crash, error, timeout, 500, exception, failed to load, network failure
    - high: invalid, not found, unexpected, wrong, assertion, regression, schema regression, quality failure
    - medium: missing, slow, layout, display, visible
    - low: typo, spacing, color
    """
    err = error_message.lower()
    
    # Critical keywords
    critical_kws = ['crash', 'error', 'timeout', '500', 'exception', 'failed to load', 'not reachable', 'network failures']
    if any(kw in err for kw in critical_kws):
        return 'critical'
        
    # High keywords
    high_kws = ['invalid', 'not found', 'unexpected', 'wrong', 'assertion', 'regression', 'schema regression', 'quality failures']
    if any(kw in err for kw in high_kws):
        return 'high'
        
    # Medium keywords
    medium_kws = ['missing', 'slow', 'layout', 'display', 'visible', 'wait_for']
    if any(kw in err for kw in medium_kws):
        return 'medium'
        
    # Low keywords
    low_kws = ['typo', 'spacing', 'color']
    if any(kw in err for kw in low_kws):
        return 'low'
        
    return 'medium'


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

    # Fetch failed results
    failed_results = TestResult.objects.filter(test_run=test_run, status='FAILED')
    
    bugs_created = 0
    
    try:
        with transaction.atomic():
            # Clear previous bugs for this test case to avoid duplicates across runs
            Bug.objects.filter(test_run__test_case=test_run.test_case).delete()
            
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
                                
                # Create Bug
                Bug.objects.create(
                    test_run=test_run,
                    title=title,
                    description=description,
                    severity=severity,
                    api_endpoint=matched_endpoint
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
