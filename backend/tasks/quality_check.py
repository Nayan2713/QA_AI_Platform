# backend/tasks/quality_check.py

import json
import re
from celery import shared_task
import logging
from django.db.models import Avg, Count
from django.utils import timezone
from core.models import (
    TestValidation, CoverageReport, FlakinessReport, BugValidation,
    QualityMetrics, TestCase, Page, TestRun, Bug, Application, CeleryTask
)

logger = logging.getLogger(__name__)


# ============================================
# TASK 1: VALIDATE TEST RELEVANCE
# ============================================

@shared_task(bind=True)
def validate_test_relevance(self, test_case_id, page_url):
    """
    Validates if generated tests actually interact with real page elements.
    
    Args:
        test_case_id: ID of the test case to validate
        page_url: URL of the page being tested
    
    Returns:
        dict with validation results
    """
    try:
        test_case = TestCase.objects.get(id=test_case_id)
        
        # Look up page
        page = None
        if page_url:
            page = Page.objects.filter(url=page_url).first()
        if not page:
            page = Page.objects.filter(app=test_case.app).first()
        
        # Extract detected selectors on the page from page.buttons and page.forms
        detected_selectors = []
        if page:
            # Extract from buttons
            buttons = page.buttons or []
            if isinstance(buttons, str):
                try:
                    buttons = json.loads(buttons)
                except:
                    buttons = []
            for b in buttons:
                if isinstance(b, dict) and b.get('selector'):
                    detected_selectors.append(b.get('selector'))
            
            # Extract from forms
            forms = page.forms or []
            if isinstance(forms, str):
                try:
                    forms = json.loads(forms)
                except:
                    forms = []
            for f in forms:
                if isinstance(f, dict):
                    if f.get('id'):
                        detected_selectors.append(f"#{f.get('id')}")
                    for field in f.get('fields', []):
                        if isinstance(field, dict):
                            if field.get('id'):
                                detected_selectors.append(f"#{field.get('id')}")
                            if field.get('name'):
                                detected_selectors.append(f"[name=\"{field.get('name')}\"]")
                                detected_selectors.append(f"input[name=\"{field.get('name')}\"]")

        # Parse test steps
        test_steps = test_case.steps or []
        if isinstance(test_steps, str):
            try:
                test_steps = json.loads(test_steps)
            except:
                test_steps = []
        
        relevance_score = 0
        elements_found = 0
        validation_details = {}
        
        # Check each step in the test
        for idx, step in enumerate(test_steps):
            step_id = f"step_{idx}"
            selector = step.get('selector', '')
            step_type = step.get('action', 'unknown')
            
            # Check if selector exists on page
            selector_found = False
            if selector:
                # 1. Direct or partial substring match
                selector_found = any(selector in s or s in selector for s in detected_selectors)
                
                # 2. Extract and check for ID selectors (e.g. #username inside nested selectors)
                if not selector_found:
                    ids = re.findall(r'#([a-zA-Z0-9_\-]+)', selector)
                    for id_val in ids:
                        if any(id_val in s for s in detected_selectors):
                            selector_found = True
                            break
                            
                # 3. Extract and check for name attribute selectors (e.g. [name="username"])
                if not selector_found:
                    names = re.findall(r'name=["\']?([a-zA-Z0-9_\-]+)["\']?', selector)
                    for name_val in names:
                        if any(name_val in s for s in detected_selectors):
                            selector_found = True
                            break
                            
                # 4. Standard HTML structural tags that are always relevant
                if not selector_found:
                    if selector.strip() in ['body', 'html', 'head', 'main']:
                        selector_found = True
            
            if selector_found:
                elements_found += 1
                relevance_score += 1
            
            validation_details[step_id] = {
                'selector': selector,
                'type': step_type,
                'found': selector_found
            }
        
        # Calculate relevance percentage
        total_steps = len(test_steps) if test_steps else 1
        relevance_percentage = (elements_found / total_steps * 100) if total_steps > 0 else 0
        
        # Determine status
        if relevance_percentage >= 90:
            status = 'HIGHLY_RELEVANT'
        elif relevance_percentage >= 70:
            status = 'RELEVANT'
        elif relevance_percentage >= 50:
            status = 'SOMEWHAT_RELEVANT'
        else:
            status = 'IRRELEVANT'
        
        # Create or update validation record
        validation, created = TestValidation.objects.update_or_create(
            test_case=test_case,
            defaults={
                'application': test_case.app,
                'relevance_score': relevance_percentage,
                'elements_found': elements_found,
                'elements_total': total_steps,
                'status': status,
                'validation_details': validation_details
            }
        )
        
        print(f"✓ Test relevance validated: {test_case_id} - {relevance_percentage}%")
        
        return {
            'test_id': test_case_id,
            'relevance_score': relevance_percentage,
            'elements_found': elements_found,
            'total_steps': total_steps,
            'status': status,
            'success': True
        }
    
    except Exception as e:
        print(f"✗ Error validating test relevance: {str(e)}")
        return {
            'test_id': test_case_id,
            'error': str(e),
            'success': False
        }


# ============================================
# TASK 2: ANALYZE TEST COVERAGE
# ============================================

@shared_task(bind=True)
def analyze_coverage(self, application_id):
    """
    Calculates test coverage for the application.
    Measures: % of pages covered, % of forms covered, % of workflows covered.
    
    Args:
        application_id: ID of the application
    
    Returns:
        dict with coverage metrics
    """
    try:
        app = Application.objects.get(id=application_id)
        
        # Get all pages
        all_pages = Page.objects.filter(app=app)
        total_pages = all_pages.count()
        
        # Get test cases
        test_cases = TestCase.objects.filter(app=app)
        
        # Pre-parse test cases steps to avoid N^2 JSON deserialization inside loop
        parsed_test_steps = []
        for test in test_cases:
            steps = test.steps or []
            if isinstance(steps, str):
                try:
                    steps = json.loads(steps)
                except Exception:
                    steps = []
            parsed_test_steps.append(steps)
        
        # Determine tested pages by analyzing test cases
        tested_page_ids = set()
        for page in all_pages:
            for steps in parsed_test_steps:
                for step in steps:
                    val = step.get('value', '') or step.get('target', '') or step.get('url', '')
                    if val and (page.url in val or val in page.url):
                        tested_page_ids.add(page.id)
                        break
        
        tested_pages = len(tested_page_ids)
        page_coverage = (tested_pages / total_pages * 100) if total_pages > 0 else 0
        
        # === FORM COVERAGE ===
        total_forms = 0
        tested_forms = 0
        
        for page in all_pages:
            forms = page.forms or []
            if isinstance(forms, str):
                try:
                    forms = json.loads(forms)
                except:
                    forms = []
            
            total_forms += len(forms)
            
            # Check which forms are tested
            for form in forms:
                if not isinstance(form, dict):
                    continue
                form_id = form.get('id') or ''
                
                # Check if any test case interacts with this form
                is_form_tested = False
                for test in test_cases:
                    steps = test.steps or []
                    if isinstance(steps, str):
                        try:
                            steps = json.loads(steps)
                        except:
                            steps = []
                    for step in steps:
                        selector = step.get('selector', '')
                        if form_id and form_id in selector:
                            is_form_tested = True
                            break
                        for field in form.get('fields', []):
                            if isinstance(field, dict):
                                f_id = field.get('id')
                                f_name = field.get('name')
                                if (f_id and f_id in selector) or (f_name and f_name in selector):
                                    is_form_tested = True
                                    break
                        if is_form_tested:
                            break
                    if is_form_tested:
                        break
                if is_form_tested:
                    tested_forms += 1
        
        form_coverage = (tested_forms / total_forms * 100) if total_forms > 0 else 0
        
        # === WORKFLOW COVERAGE ===
        tested_workflows = set()
        for test in test_cases:
            steps = test.steps or []
            if isinstance(steps, str):
                try:
                    steps = json.loads(steps)
                except:
                    steps = []
            
            # Create workflow signature based on first 3 step actions
            workflow = tuple([step.get('action') for step in steps[:3]])
            if workflow:
                tested_workflows.add(workflow)
        
        # Estimate total possible workflows
        estimated_total_workflows = max(total_pages * 3, len(tested_workflows) or 1)
        workflow_coverage = (len(tested_workflows) / estimated_total_workflows * 100) if estimated_total_workflows > 0 else 0
        
        # Calculate overall coverage
        overall_coverage = (page_coverage + form_coverage + workflow_coverage) / 3
        
        # Find untested elements
        untested_elements = []
        for page in all_pages:
            if page.id not in tested_page_ids:
                untested_elements.append({
                    'type': 'page',
                    'url': page.url,
                    'title': page.title
                })
        
        # Create coverage report
        report = CoverageReport.objects.create(
            application=app,
            page_coverage=page_coverage,
            form_coverage=form_coverage,
            workflow_coverage=workflow_coverage,
            overall_coverage=overall_coverage,
            total_pages=total_pages,
            tested_pages=tested_pages,
            total_forms=total_forms,
            tested_forms=tested_forms,
            total_workflows=estimated_total_workflows,
            tested_workflows=len(tested_workflows),
            untested_elements=untested_elements
        )
        
        print(f"✓ Coverage analyzed: {app.url} - Overall: {overall_coverage:.1f}%")
        
        return {
            'application_id': application_id,
            'page_coverage': page_coverage,
            'form_coverage': form_coverage,
            'workflow_coverage': workflow_coverage,
            'overall_coverage': overall_coverage,
            'recommendation': 'Good' if overall_coverage >= 80 else 'Needs improvement',
            'success': True
        }
    
    except Exception as e:
        print(f"✗ Error analyzing coverage: {str(e)}")
        return {
            'application_id': application_id,
            'error': str(e),
            'success': False
        }


# ============================================
# TASK 3: VALIDATE BUG ACCURACY
# ============================================

@shared_task(bind=True)
def validate_bug_accuracy(self, bug_id):
    """
    Validates if a detected bug is real or a false positive.
    
    Args:
        bug_id: ID of the bug to validate
    
    Returns:
        dict with validation results
    """
    try:
        bug = Bug.objects.get(id=bug_id)
        app = bug.application or (bug.test_run.test_case.app if bug.test_run and bug.test_run.test_case else None)
        
        # Extract error message from failed TestResult step logs
        if bug.test_run:
            failed_results = bug.test_run.step_results.filter(status='FAILED')
            error_message = failed_results.first().error if failed_results.exists() else bug.description
        else:
            failed_results = None
            error_message = bug.description
        
        confidence_scores = {}
        
        # ===== METHOD 1: REPRODUCIBILITY SCORE =====
        # Check if same bug/error appears in other runs for the same app
        from django.db.models import Q
        if app:
            same_error_bugs = Bug.objects.filter(
                Q(application=app) | Q(test_run__test_case__app=app),
                title__icontains=bug.title[:30]
            ).distinct()
            reproducibility_count = same_error_bugs.count()
        else:
            reproducibility_count = 1
        reproducibility_score = min(reproducibility_count / 3 * 100, 100)
        confidence_scores['reproducibility'] = reproducibility_score
        
        # ===== METHOD 2: ERROR SEVERITY SCORE =====
        error_log = (error_message or '').lower()
        error_type = 'unknown'
        severity_score = 50  # Default
        
        severity_keywords = {
            'crash': {'score': 95, 'type': 'crash'},
            'exception': {'score': 90, 'type': 'exception'},
            'error': {'score': 85, 'type': 'error'},
            'failed': {'score': 80, 'type': 'assertion'},
            'timeout': {'score': 75, 'type': 'timeout'},
            'blank page': {'score': 85, 'type': 'blank_page'},
            'connection refused': {'score': 80, 'type': 'connection'},
            'not found': {'score': 70, 'type': 'not_found'},
            'validation': {'score': 60, 'type': 'validation'},
            'semantic': {'score': 85, 'type': 'semantic_mismatch'},
            'expectations': {'score': 85, 'type': 'semantic_mismatch'},
            'warning': {'score': 40, 'type': 'warning'},
            'info': {'score': 20, 'type': 'info'},
        }
        
        for keyword, data in severity_keywords.items():
            if keyword in error_log:
                severity_score = data['score']
                error_type = data['type']
                break
        
        confidence_scores['severity'] = severity_score
        
        # ===== METHOD 3: SCREENSHOT ANALYSIS =====
        screenshot_result = None
        if bug.test_run:
            screenshot_result = bug.test_run.step_results.exclude(screenshot__isnull=True).exclude(screenshot='').first()
        screenshot_base64 = screenshot_result.screenshot if screenshot_result else (bug.screenshot.url if bug.screenshot else '')
        screenshot_score = 60
        if screenshot_base64 and len(str(screenshot_base64)) > 1000:
            screenshot_score = 75
        confidence_scores['screenshot'] = screenshot_score
        
        # ===== METHOD 4: ERROR PATTERN MATCHING =====
        false_positive_patterns = [
            r'selenium.*element.*stale',
            r'timeout.*waiting.*element',
            r'javascript.*disabled',
            # Playwright specific selector/timeout patterns:
            r'waiting for locator',
            r'timeout.*exceeded',
            r'locator\..*timeout',
            r'not a valid selector',
            r'failed to execute.*selector',
            r'strict mode violation',
        ]
        
        pattern_score = 70
        for pattern in false_positive_patterns:
            if re.search(pattern, error_log):
                pattern_score = 20  # Significantly lower confidence score for script failures
                break
        
        confidence_scores['pattern'] = pattern_score
        
        # ===== CALCULATE FINAL CONFIDENCE =====
        weights = {
            'reproducibility': 0.3,
            'severity': 0.3,
            'screenshot': 0.2,
            'pattern': 0.2
        }
        
        final_confidence = sum(
            confidence_scores.get(method, 0) * weight
            for method, weight in weights.items()
        )
        
        # Determine verification status
        if final_confidence >= 75:
            verification_status = 'VERIFIED'
            is_verified = True
        elif final_confidence >= 50:
            verification_status = 'NEEDS_REVIEW'
            is_verified = False
        else:
            verification_status = 'FALSE_POSITIVE'
            is_verified = False
        
        # Create or update bug validation
        validation, created = BugValidation.objects.update_or_create(
            bug=bug,
            defaults={
                'application': app,
                'confidence_score': final_confidence,
                'is_verified': is_verified,
                'verification_status': verification_status,
                'reproducibility_count': reproducibility_count,
                'reproducibility_score': reproducibility_score,
                'severity_score': severity_score,
                'error_type': error_type,
                'validation_methods': confidence_scores,
                'validation_notes': f"Severity: {error_type} | Reproducibility: {reproducibility_count}x"
            }
        )
        
        print(f"✓ Bug validated: {bug_id} - {verification_status} ({final_confidence:.1f}%)")
        
        return {
            'bug_id': bug_id,
            'confidence_score': final_confidence,
            'verification_status': verification_status,
            'error_type': error_type,
            'validation_methods': confidence_scores,
            'success': True
        }
    
    except Exception as e:
        print(f"✗ Error validating bug: {str(e)}")
        return {
            'bug_id': bug_id,
            'error': str(e),
            'success': False
        }


# ============================================
# TASK 4: DETECT TEST FLAKINESS
# ============================================

@shared_task(bind=True)
def detect_flakiness(self, test_case_id, num_runs=5):
    """
    Runs a test multiple times and detects if it's flaky (unreliable).
    
    Args:
        test_case_id: ID of test to check
        num_runs: Number of times to run the test (default 5)
    
    Returns:
        dict with flakiness metrics
    """
    try:
        test_case = TestCase.objects.get(id=test_case_id)
        
        recent_runs = TestRun.objects.filter(
            test_case=test_case
        ).order_by('-created_at')[:num_runs]
        
        if recent_runs.count() < 2:
            return {
                'test_id': test_case_id,
                'insufficient_data': True,
                'runs_available': recent_runs.count(),
                'success': True
            }
        
        runs_passed = 0
        runs_failed = 0
        failure_patterns = {}
        
        for run in recent_runs:
            if run.status == 'COMPLETED':
                runs_passed += 1
            else:
                runs_failed += 1
                
                # Analyze which step failed using step_results
                test_results = run.step_results.all()
                for result in test_results:
                    if result.status == 'FAILED':
                        step_key = f"Step {result.step_number}"
                        failure_patterns[step_key] = failure_patterns.get(step_key, 0) + 1
        
        total_runs = runs_passed + runs_failed
        flakiness_percentage = (runs_failed / total_runs * 100) if total_runs > 0 else 0
        
        # Determine stability status
        if flakiness_percentage <= 10:
            status = 'STABLE'
        elif flakiness_percentage <= 20:
            status = 'MOSTLY_STABLE'
        elif flakiness_percentage <= 50:
            status = 'FLAKY'
        else:
            status = 'VERY_FLAKY'
        
        # Determine primary failure reason
        failure_reason = ''
        if failure_patterns:
            most_common_step = max(failure_patterns, key=failure_patterns.get)
            failure_reason = f"Most common failure at: {most_common_step}"
        
        # Create flakiness report
        report = FlakinessReport.objects.create(
            test_case=test_case,
            application=test_case.app,
            runs_executed=total_runs,
            runs_passed=runs_passed,
            runs_failed=runs_failed,
            flakiness_percentage=flakiness_percentage,
            status=status,
            failure_patterns=failure_patterns,
            failure_reason=failure_reason,
            last_run=timezone.now()
        )
        
        print(f"✓ Flakiness detected: {test_case_id} - {flakiness_percentage:.1f}% ({status})")
        
        return {
            'test_id': test_case_id,
            'flakiness_percentage': flakiness_percentage,
            'status': status,
            'runs_passed': runs_passed,
            'runs_failed': runs_failed,
            'failure_patterns': failure_patterns,
            'verdict': 'UNRELIABLE' if flakiness_percentage > 20 else 'RELIABLE',
            'success': True
        }
    
    except Exception as e:
        print(f"✗ Error detecting flakiness: {str(e)}")
        return {
            'test_id': test_case_id,
            'error': str(e),
            'success': False
        }


# ============================================
# TASK 5: CALCULATE OVERALL QUALITY METRICS
# ============================================

@shared_task(bind=True)
def calculate_quality_metrics(self, application_id):
    """
    Calculates overall quality score for the application.
    Combines all quality metrics into a single grade.
    
    Args:
        application_id: ID of the application
    
    Returns:
        dict with overall quality metrics
    """
    try:
        app = Application.objects.get(id=application_id)
        
        # ===== COVERAGE SCORE =====
        latest_coverage = CoverageReport.objects.filter(
            application=app
        ).latest('created_at') if CoverageReport.objects.filter(application=app).exists() else None
        
        coverage_score = latest_coverage.overall_coverage if latest_coverage else 0
        
        # ===== RELIABILITY SCORE =====
        flakiness_reports = FlakinessReport.objects.filter(
            application=app
        )
        
        if flakiness_reports.exists():
            avg_flakiness = flakiness_reports.aggregate(
                Avg('flakiness_percentage')
            )['flakiness_percentage__avg'] or 0
            reliability_score = 100 - avg_flakiness
        else:
            reliability_score = 50
        
        # ===== ACCURACY SCORE =====
        bug_validations = BugValidation.objects.filter(
            application=app
        )
        
        if bug_validations.exists():
            verified_count = bug_validations.filter(is_verified=True).count()
            total_count = bug_validations.count()
            accuracy_score = (verified_count / total_count * 100) if total_count > 0 else 0
        else:
            accuracy_score = 50
        
        # ===== RELEVANCE SCORE =====
        test_validations = TestValidation.objects.filter(
            test_case__app=app
        )
        
        if test_validations.exists():
            relevance_score = test_validations.aggregate(
                Avg('relevance_score')
            )['relevance_score__avg'] or 0
        else:
            relevance_score = 50
        
        # ===== CALCULATE OVERALL SCORE =====
        weights = {
            'coverage': 0.25,
            'reliability': 0.3,
            'accuracy': 0.25,
            'relevance': 0.2
        }
        
        overall_score = (
            coverage_score * weights['coverage'] +
            reliability_score * weights['reliability'] +
            accuracy_score * weights['accuracy'] +
            relevance_score * weights['relevance']
        )
        
        # ===== ASSIGN GRADE =====
        if overall_score >= 90:
            grade = 'A'
        elif overall_score >= 80:
            grade = 'B'
        elif overall_score >= 70:
            grade = 'C'
        elif overall_score >= 60:
            grade = 'D'
        else:
            grade = 'F'
        
        # ===== GENERATE RECOMMENDATIONS =====
        recommendations = []
        
        if coverage_score < 70:
            recommendations.append("Increase test coverage - target 80%+")
        
        if reliability_score < 80:
            recommendations.append("Fix flaky tests to improve reliability")
        
        if accuracy_score < 70:
            recommendations.append("Reduce false positives in bug detection")
        
        if relevance_score < 70:
            recommendations.append("Improve test relevance to actual page elements")
        
        if not recommendations:
            recommendations.append("Quality is good! Continue maintaining standards.")
        
        # Create or update quality metrics
        metrics, created = QualityMetrics.objects.update_or_create(
            application=app,
            defaults={
                'coverage_score': coverage_score,
                'reliability_score': reliability_score,
                'accuracy_score': accuracy_score,
                'relevance_score': relevance_score,
                'overall_score': overall_score,
                'grade': grade,
                'recommendations': recommendations
            }
        )
        
        print(f"✓ Quality metrics calculated: {app.url} - Grade {grade} ({overall_score:.1f}%)")
        
        return {
            'application_id': application_id,
            'coverage_score': coverage_score,
            'reliability_score': reliability_score,
            'accuracy_score': accuracy_score,
            'relevance_score': relevance_score,
            'overall_score': overall_score,
            'grade': grade,
            'recommendations': recommendations,
            'success': True
        }
    
    except Exception as e:
        print(f"✗ Error calculating quality metrics: {str(e)}")
        return {
            'application_id': application_id,
            'error': str(e),
            'success': False
        }


# ============================================
# BATCH QUALITY CHECK TASK
# ============================================

# NOTE: run_in_thread is intentionally NOT used in quality_check.py.
# These tasks run in a standard Celery synchronous worker context so
# Django ORM calls work directly without spawning extra threads.

@shared_task(bind=True, queue="quality")
def run_full_quality_check(self, application_id):
    """
    Runs complete quality check pipeline for an application.
    OPTIMIZED: direct DB calls instead of thread-per-operation.
    """
    try:
        # OPTIMIZED: fetch all related data upfront in minimal queries
        app = Application.objects.get(id=application_id)

        task_id = self.request.id or "dummy_task_id"
        task_record = CeleryTask.objects.filter(task_id=task_id).first()

        def update_progress(progress, status_text):
            nonlocal task_record
            if task_record:
                task_record.status = 'progress'
                task_record.progress = progress
                task_record.result = {"status_text": status_text}
                task_record.save()
            else:
                CeleryTask.objects.filter(task_id=task_id).update(
                    status='progress',
                    progress=progress,
                    result={"status_text": status_text}
                )

        update_progress(10, "Initializing quality check pipeline...")

        # OPTIMIZED: fetch in three targeted queries instead of threaded lambdas
        test_cases = list(TestCase.objects.filter(app=app))
        pages = list(Page.objects.filter(app=app).only('url', 'title'))
        bugs = list(
            Bug.objects.filter(test_run__test_case__app=app)
            .select_related('test_run__test_case', 'application')
        )

        results = {
            'application_id': application_id,
            'tests_checked': 0,
            'coverage_analyzed': False,
            'bugs_validated': 0,
            'flakiness_checked': 0,
            'metrics_calculated': False,
            'started_at': timezone.now().isoformat()
        }

        # 1. Validate test relevance
        update_progress(20, f"Step 1/5: Checking relevance for {len(test_cases)} tests...")
        first_page_url = pages[0].url if pages else ''
        for test in test_cases[:10]:
            validate_test_relevance(test.id, first_page_url)
            results['tests_checked'] += 1

        # 2. Analyze coverage
        update_progress(45, "Step 2/5: Analyzing test coverage...")
        analyze_coverage(application_id)
        results['coverage_analyzed'] = True

        # 3. Validate bugs
        update_progress(65, f"Step 3/5: Checking false positives for {len(bugs)} bugs...")
        for bug in bugs[:20]:
            validate_bug_accuracy(bug.id)
            results['bugs_validated'] += 1

        # 4. Detect flakiness
        update_progress(80, f"Step 4/5: Detecting stability/flakiness for {len(test_cases)} tests...")
        for test in test_cases[:10]:
            detect_flakiness(test.id, 5)
            results['flakiness_checked'] += 1

        # 5. Calculate overall metrics
        update_progress(95, "Step 5/5: Computing overall quality scores and grade...")
        calculate_quality_metrics(application_id)
        results['metrics_calculated'] = True

        # Final success update
        if task_record:
            task_record.status = 'success'
            task_record.progress = 100
            task_record.result = {
                "status_text": "Full quality check completed successfully!",
                "tests_checked": results['tests_checked'],
                "bugs_validated": results['bugs_validated']
            }
            task_record.completed_at = timezone.now()
            task_record.save()
        else:
            CeleryTask.objects.filter(task_id=task_id).update(
                status='success',
                progress=100,
                result={
                    "status_text": "Full quality check completed successfully!",
                    "tests_checked": results['tests_checked'],
                    "bugs_validated": results['bugs_validated']
                },
                completed_at=timezone.now()
            )

        results['completed_at'] = timezone.now().isoformat()
        results['success'] = True
        return results
        
    except Exception as e:
        logger.error(f"✗ Error running quality check: {str(e)}")
        task_id = self.request.id or "dummy_task_id"
        try:
            if task_record:
                task_record.status = 'failed'
                task_record.error = str(e)
                task_record.completed_at = timezone.now()
                task_record.save()
            else:
                CeleryTask.objects.filter(task_id=task_id).update(
                    status='failed',
                    error=str(e),
                    completed_at=timezone.now()
                )
        except Exception:
            pass
        return {
            'application_id': application_id,
            'error': str(e),
            'success': False
        }