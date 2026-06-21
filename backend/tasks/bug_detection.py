import logging
from celery import shared_task
from django.db import transaction

from core.models import TestRun, TestResult, Bug

logger = logging.getLogger(__name__)

def classify_severity(error_message):
    """
    Classifies bug severity based on keywords present in the error message.
    - critical: crash, error, timeout, 500, exception, failed to load
    - high: invalid, not found, unexpected, wrong, assertion
    - medium: missing, slow, layout, display, visible
    - low: typo, spacing, color
    """
    err = error_message.lower()
    
    # Critical keywords
    critical_kws = ['crash', 'error', 'timeout', '500', 'exception', 'failed to load', 'not reachable']
    if any(kw in err for kw in critical_kws):
        return 'critical'
        
    # High keywords
    high_kws = ['invalid', 'not found', 'unexpected', 'wrong', 'assertion']
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
                
                details_parts = []
                if selector: details_parts.append(f"selector '{selector}'")
                if target: details_parts.append(f"target '{target}'")
                if value: details_parts.append(f"value '{value}'")
                details_str = ", ".join(details_parts)
                
                description = (
                    f"During the execution of test step {step_num} doing '{action}', an error occurred.\n"
                    f"Action details: {details_str if details_str else 'none'}\n"
                    f"Error output:\n{error_msg}"
                )
                
                # Create Bug
                Bug.objects.create(
                    test_run=test_run,
                    title=title,
                    description=description,
                    severity=severity
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
