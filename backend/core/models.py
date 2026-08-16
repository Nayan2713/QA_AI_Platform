from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
import base64
import hashlib
from cryptography.fernet import Fernet
from .enums import (
    ApplicationStatus, LoginStatus, TestCaseValidationStatus,
    TestRunStatus, TestResultStatus, BugSeverity, CeleryTaskStatus,
    TestValidationStatus, FlakinessStatus, VerificationStatus, QualityGrade,
)

def _get_fernet():
    """Return a Fernet cipher.

    Prefers a dedicated ``FERNET_KEY`` env var (a 32-byte URL-safe base64
    string).  If that is not set, derives a stable key from SECRET_KEY
    using PBKDF2 so that normal SECRET_KEY rotation does **not** silently
    corrupt previously-encrypted values—as long as the derived key is
    migrated first.
    """
    explicit = getattr(settings, 'FERNET_KEY', None)
    if explicit:
        return Fernet(explicit.encode() if isinstance(explicit, str) else explicit)

    # Derive a stable 32-byte key from SECRET_KEY via PBKDF2
    dk = hashlib.pbkdf2_hmac(
        'sha256',
        settings.SECRET_KEY.encode(),
        b'EncryptedCharField-salt',
        iterations=100_000,
        dklen=32,
    )
    return Fernet(base64.urlsafe_b64encode(dk))


class EncryptedCharField(models.TextField):
    """
    FIX: Stores values encrypted at rest using Fernet symmetric encryption.
    Transparently encrypts on save and decrypts on load.
    """
    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        if value.startswith('gAAAAA'):
            try:
                return _get_fernet().decrypt(value.encode()).decode()
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Fernet decryption failed for encrypted field: {e}")
                return None
        return value  # unencrypted legacy string

    def to_python(self, value):
        return value  # already a plain string in memory

    def get_prep_value(self, value):
        if value is None:
            return value
        return _get_fernet().encrypt(value.encode()).decode()


class Application(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
    url = models.URLField(max_length=500)
    base_url = models.URLField(max_length=500)
    login_url = models.URLField(max_length=500, blank=True, null=True)
    username = models.CharField(max_length=255, blank=True, null=True)
    # FIX: store the target-site password encrypted at rest
    password = EncryptedCharField(blank=True, null=True)
    status = models.CharField(
        max_length=20, choices=ApplicationStatus.choices,
        default=ApplicationStatus.IDLE, db_index=True,
    )
    discovery_source = models.CharField(max_length=20, blank=True, null=True) # 'mcp' or 'browser'
    login_status = models.CharField(
        max_length=20, choices=LoginStatus.choices,
        default=LoginStatus.NOT_ATTEMPTED,
    )
    storage_state = models.TextField(blank=True, null=True)
    login_error = models.TextField(blank=True, null=True)
    industry = models.CharField(max_length=100, blank=True, null=True)
    use_llm_in_crawl = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.url} ({self.user.username})"


class Page(models.Model):
    app = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='pages')
    url = models.URLField(max_length=1000)
    title = models.CharField(max_length=500, blank=True, null=True)
    forms = models.JSONField(default=list)  # [{"id": "...", "fields": [...], "action": "...", "method": "..."}]
    buttons = models.JSONField(default=list)  # [{"text": "...", "selector": "..."}]
    page_type = models.CharField(max_length=64, blank=True, null=True)
    elements = models.JSONField(default=dict, blank=True, null=True)
    workflows = models.JSONField(default=list, blank=True, null=True)
    accessibility_roles = models.JSONField(default=list, blank=True, null=True)
    connections = models.JSONField(default=list, blank=True, null=True)
    semantic_metadata = models.JSONField(default=dict, blank=True, null=True)
    ai_summary = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.title or self.url} in {self.app.url}"


class TestCase(models.Model):
    app = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='test_cases')
    title = models.CharField(max_length=255)
    steps = models.JSONField(default=list)  # [{"action": "...", "selector": "...", "value": "..."}]
    expected_result = models.TextField()
    ai_generated = models.BooleanField(default=True)
    category = models.CharField(max_length=32, default="Generic")
    validation_status = models.CharField(
        max_length=20,
        choices=TestCaseValidationStatus.choices,
        default=TestCaseValidationStatus.DRAFT,
    )
    generation_context = models.JSONField(default=dict, blank=True, null=True)
    self_healed_count = models.IntegerField(default=0)
    consecutive_flips = models.IntegerField(default=0)
    flakiness_score = models.FloatField(default=0.0)
    is_flaky = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.title} - {self.app.url}"


class TestRun(models.Model):
    STATUS_CHOICES = TestRunStatus.choices
    test_case = models.ForeignKey(TestCase, on_delete=models.CASCADE, related_name='test_runs')
    status = models.CharField(
        max_length=20, choices=TestRunStatus.choices,
        default=TestRunStatus.PENDING, db_index=True,
    )
    metadata = models.JSONField(default=dict, blank=True)
    bugs_found = models.IntegerField(default=0)
    self_healed_count = models.IntegerField(default=0)
    execution_duration_ms = models.IntegerField(default=0, null=True, blank=True)
    execution_mode = models.CharField(max_length=32, default="HEADLESS", null=True, blank=True)
    js_coverage_pct = models.FloatField(default=0.0, null=True, blank=True)
    css_coverage_pct = models.FloatField(default=0.0, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"Run {self.id} for {self.test_case.title} ({self.status})"


class TestResult(models.Model):
    STATUS_CHOICES = TestResultStatus.choices
    test_run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='step_results')
    step_number = models.IntegerField()
    status = models.CharField(max_length=20, choices=TestResultStatus.choices)
    error = models.TextField(blank=True, null=True)
    screenshot = models.TextField(blank=True, null=True)  # base64 encoded image or relative file path
    auto_healed = models.BooleanField(default=False)
    healing_details = models.JSONField(default=dict, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"Result Step {self.step_number} in Run {self.test_run.id} ({self.status})"


class APIEndpoint(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='api_endpoints')
    method = models.CharField(max_length=10)
    url_pattern = models.CharField(max_length=1000)
    request_schema = models.JSONField(default=dict, blank=True)
    response_schema = models.JSONField(default=dict, blank=True)
    auth_type = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True,
     db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('application', 'method', 'url_pattern')
        ordering = ['url_pattern']

    def __str__(self):
        return f"[{self.method}] {self.url_pattern}"


class Bug(models.Model):
    SEVERITY_CHOICES = BugSeverity.choices
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='bugs', null=True, blank=True)
    test_run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='bugs', null=True, blank=True)
    bug_type = models.CharField(max_length=64, blank=True, null=True)
    severity = models.CharField(
        max_length=20, choices=BugSeverity.choices,
        default=BugSeverity.MEDIUM, db_index=True,
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    steps_to_reproduce = models.JSONField(default=list, blank=True, null=True)
    screenshot = models.ImageField(upload_to='bugs/', null=True, blank=True)
    element_selector = models.CharField(max_length=512, null=True, blank=True)
    status = models.CharField(max_length=32, default='open')
    api_endpoint = models.ForeignKey(APIEndpoint, on_delete=models.SET_NULL, blank=True, null=True, related_name='bugs')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"[{self.severity.upper()}] {self.title}"

class AgentSession(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='agent_sessions')
    task_type = models.CharField(max_length=64)   # discovery, test_execution, bug_detection
    status = models.CharField(max_length=32)      # running, completed, failed
    llm_model = models.CharField(max_length=128)
    steps_taken = models.JSONField(default=list)  # log of agent actions
    tokens_used = models.IntegerField(default=0)
    duration_seconds = models.FloatField(null=True)
    result_summary = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.task_type.upper()} session for {self.application.url} ({self.status})"

class CeleryTask(models.Model):
    """Track all celery tasks"""
    TASK_STATUS_CHOICES = CeleryTaskStatus.choices
    
    app = models.ForeignKey(Application, on_delete=models.CASCADE, null=True, blank=True, related_name='celery_tasks')
    task_id = models.CharField(max_length=255, unique=True)
    task_type = models.CharField(max_length=100)  # 'discovery', 'test_gen', etc
    status = models.CharField(
        max_length=20, choices=CeleryTaskStatus.choices, db_index=True,
    )
    progress = models.IntegerField(default=0)  # 0-100
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.task_type} - {self.task_id}"
    


class TestValidation(models.Model):
    test_case = models.OneToOneField(TestCase, on_delete=models.CASCADE, related_name='quality_validation')
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name='test_validations',
        null=True,      # ADD THIS
        blank=True      # ADD THIS
    )
    relevance_score = models.FloatField(default=0)
    elements_found = models.IntegerField(default=0)
    elements_total = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=TestValidationStatus.choices,
        default=TestValidationStatus.IRRELEVANT,
        db_index=True,
    )
    validation_details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class CoverageReport(models.Model):
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name='coverage_reports',
        null=True,      # ADD THIS
        blank=True      # ADD THIS
    )
    page_coverage = models.FloatField(default=0)
    form_coverage = models.FloatField(default=0)
    workflow_coverage = models.FloatField(default=0)
    overall_coverage = models.FloatField(default=0)
    total_pages = models.IntegerField(default=0)
    tested_pages = models.IntegerField(default=0)
    total_forms = models.IntegerField(default=0)
    tested_forms = models.IntegerField(default=0)
    total_workflows = models.IntegerField(default=0)
    tested_workflows = models.IntegerField(default=0)
    untested_elements = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class FlakinessReport(models.Model):
    test_case = models.ForeignKey(
        TestCase,
        on_delete=models.CASCADE,
        related_name='flakiness_reports',
        null=True,      # ADD THIS
        blank=True      # ADD THIS
    )
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name='flakiness_reports',
        null=True,      # ADD THIS
        blank=True      # ADD THIS
    )
    runs_executed = models.IntegerField(default=5)
    runs_passed = models.IntegerField(default=0)
    runs_failed = models.IntegerField(default=0)
    flakiness_percentage = models.FloatField(default=0)
    status = models.CharField(
        max_length=20,
        choices=FlakinessStatus.choices,
        default=FlakinessStatus.VERY_FLAKY,
        db_index=True,
    )
    failure_patterns = models.JSONField(default=dict)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_run = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class BugValidation(models.Model):
    bug = models.OneToOneField(
        Bug,
        on_delete=models.CASCADE,
        related_name='validation',
        null=True,      # ADD THIS
        blank=True      # ADD THIS
    )
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name='bug_validations',
        null=True,      # ADD THIS
        blank=True      # ADD THIS
    )
    confidence_score = models.FloatField(default=0)
    is_verified = models.BooleanField(default=False)
    verification_status = models.CharField(
        max_length=20,
        choices=VerificationStatus.choices,
        default=VerificationStatus.NEEDS_REVIEW,
    )
    reproducibility_count = models.IntegerField(default=1)
    reproducibility_score = models.FloatField(default=0)
    severity_score = models.FloatField(default=0)
    error_type = models.CharField(max_length=50, blank=True)
    validation_methods = models.JSONField(default=dict)
    validation_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class QualityMetrics(models.Model):
    application = models.OneToOneField(
        Application,
        on_delete=models.CASCADE,
        related_name='quality_metrics',
        null=True,      # ADD THIS
        blank=True      # ADD THIS
    )
    coverage_score = models.FloatField(default=0)
    reliability_score = models.FloatField(default=0)
    accuracy_score = models.FloatField(default=0)
    relevance_score = models.FloatField(default=0)
    overall_score = models.FloatField(default=0)
    grade = models.CharField(
        max_length=1,
        choices=QualityGrade.choices,
        default=QualityGrade.F,
    )
    recommendations = models.JSONField(default=list)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_updated']

    def __str__(self):
        app_url = self.application.url if self.application else 'N/A'
        return f"QualityMetrics for {app_url} — grade {self.grade}"


class QualityMetricsSnapshot(models.Model):
    """
    Historical companion to QualityMetrics. QualityMetrics is a OneToOne
    "current state" row that gets overwritten every time
    calculate_quality_metrics() runs, so it can never show a trend. This
    model keeps one row per calculation instead, so the dashboard can plot
    score-over-time. Written alongside QualityMetrics, never in place of it.
    """
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name='quality_snapshots'
    )
    coverage_score = models.FloatField(default=0)
    reliability_score = models.FloatField(default=0)
    accuracy_score = models.FloatField(default=0)
    relevance_score = models.FloatField(default=0)
    performance_score = models.FloatField(default=0, null=True, blank=True)
    overall_score = models.FloatField(default=0)
    grade = models.CharField(max_length=1, choices=QualityGrade.choices, default=QualityGrade.F)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        app_url = self.application.url if self.application else 'N/A'
        return f"QualityMetricsSnapshot for {app_url} @ {self.created_at:%Y-%m-%d %H:%M}"


class PerformanceThreshold(models.Model):
    """
    Latency budgets used to turn TestRun.metadata['api_calls'] entries and
    Web Vitals measurements into Bug records. One row per Application;
    application=None acts as the global default used when an app hasn't
    set its own.
    """
    application = models.OneToOneField(
        Application, on_delete=models.CASCADE,
        related_name='performance_threshold', null=True, blank=True
    )
    api_latency_warning_ms = models.IntegerField(default=500)
    api_latency_critical_ms = models.IntegerField(default=2000)
    page_load_warning_ms = models.IntegerField(default=3000)
    page_load_critical_ms = models.IntegerField(default=8000)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        app_url = self.application.url if self.application else 'GLOBAL DEFAULT'
        return f"PerformanceThreshold for {app_url}"

    @classmethod
    def for_application(cls, application):
        """Return the app's own threshold row, falling back to the global
        default (application=None), falling back to unsaved in-memory
        defaults if neither exists yet."""
        threshold = cls.objects.filter(application=application).first()
        if threshold:
            return threshold
        threshold = cls.objects.filter(application__isnull=True).first()
        if threshold:
            return threshold
        return cls()


class LoadTestResult(models.Model):
    """
    Result of firing concurrent traffic at one API endpoint via
    services.load_tester.run_load_test(). Distinct from performance-
    threshold bugs, which only observe latency from a single sequential
    browser session.
    """
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name='load_test_results'
    )
    api_endpoint = models.ForeignKey(
        APIEndpoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='load_test_results'
    )
    method = models.CharField(max_length=10, default='GET')
    url_pattern = models.CharField(max_length=1000, blank=True)
    concurrency = models.IntegerField(default=20)
    duration_seconds = models.IntegerField(default=30)
    total_requests = models.IntegerField(default=0)
    successful_requests = models.IntegerField(default=0)
    error_rate = models.FloatField(default=0)  # 0.0 - 1.0
    requests_per_second = models.FloatField(default=0)
    p50_ms = models.FloatField(default=0)
    p95_ms = models.FloatField(default=0)
    p99_ms = models.FloatField(default=0)
    max_ms = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"LoadTest [{self.method}] {self.url_pattern} @ {self.concurrency}c ({self.created_at:%Y-%m-%d %H:%M})"


class WebVitalsResult(models.Model):
    """
    Core Web Vitals + basic Performance-category signal captured via
    Playwright's PerformanceObserver bridge (services.web_vitals_scanner),
    scoped per discovered Page. Threshold breaches also get mirrored into
    Bug (bug_type='performance') so they show up in the normal bug list.
    """
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name='web_vitals_results'
    )
    page = models.ForeignKey(
        Page, on_delete=models.SET_NULL, null=True, blank=True, related_name='web_vitals_results'
    )
    url = models.URLField(max_length=1000)
    lcp_ms = models.FloatField(null=True, blank=True)   # Largest Contentful Paint
    cls_score = models.FloatField(null=True, blank=True)  # Cumulative Layout Shift
    ttfb_ms = models.FloatField(null=True, blank=True)  # Time to First Byte
    transfer_size_kb = models.FloatField(null=True, blank=True)
    performance_score = models.FloatField(default=0)  # 0-100, see web_vitals_scanner.score()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"WebVitals for {self.url} — {self.performance_score:.0f}/100"


class TeamMember(models.Model):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('member', 'Member'),
        ('viewer', 'Viewer'),
    )
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_team_members')
    member_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='team_memberships', null=True, blank=True)
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    status = models.CharField(max_length=20, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.email} ({self.role}) - Team of {self.owner.username}"


class Notification(models.Model):
    LEVEL_CHOICES = (
        ('info', 'Info'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='info')
    link = models.CharField(max_length=500, blank=True, null=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.level.upper()}] {self.title} for {self.user.username}"

# Import signals to register receivers


# ─────────────────────────────────────────────────────────────────────────────
# ADD THESE CLASSES AT THE BOTTOM OF core/models.py  (above the signals import)
# ─────────────────────────────────────────────────────────────────────────────


class VisualBaseline(models.Model):
    """
    Stores the 'correct' screenshot for a page+step pair.
    The first time a test step runs and captures a screenshot,
    we save it here. Every future run compares against this.
    """
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name='visual_baselines')
    step_number = models.IntegerField(default=0)
    screenshot_path = models.CharField(max_length=500)   # path on disk, not base64
    width = models.IntegerField(default=1280)
    height = models.IntegerField(default=800)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('page', 'step_number')
        ordering = ['-updated_at']

    def __str__(self):
        return f"Baseline page={self.page_id} step={self.step_number}"


class VisualDiff(models.Model):
    """
    Result of comparing a test run screenshot against its baseline.
    diff_percentage = 0 means pixel-perfect; > threshold means visual regression.
    """
    DIFF_STATUS = [
        ('PASSED', 'Passed'),
        ('FAILED', 'Failed'),
        ('NO_BASELINE', 'No Baseline'),
    ]
    test_run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='visual_diffs')
    baseline = models.ForeignKey(VisualBaseline, on_delete=models.SET_NULL, null=True, related_name='diffs')
    step_number = models.IntegerField(default=0)
    diff_percentage = models.FloatField(default=0.0)       # 0.0 – 100.0
    diff_screenshot_path = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=20, choices=DIFF_STATUS, default='NO_BASELINE')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"VisualDiff run={self.test_run_id} step={self.step_number} ({self.diff_percentage:.1f}%)"


class APITestCase(models.Model):
    """
    A single API-level test: method + URL + optional body/headers,
    with assertions on the HTTP status code and response body keys.
    Generated by the LLM from discovered APIEndpoint rows.
    """
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='api_test_cases')
    api_endpoint = models.ForeignKey(
        APIEndpoint, on_delete=models.SET_NULL, null=True, blank=True, related_name='api_test_cases'
    )
    title = models.CharField(max_length=255)
    method = models.CharField(max_length=10)          # GET, POST, PUT, DELETE
    url = models.CharField(max_length=1000)
    headers = models.JSONField(default=dict, blank=True)
    body = models.JSONField(default=dict, blank=True)
    expected_status = models.IntegerField(default=200)
    expected_body_contains = models.JSONField(default=list, blank=True)  # list of keys to assert exist
    auth_required = models.BooleanField(default=False)
    ai_generated = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.method}] {self.url} — {self.title}"


class APITestRun(models.Model):
    """
    One execution of an APITestCase. Records the actual HTTP response
    and whether it matched the expected assertions.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    api_test_case = models.ForeignKey(APITestCase, on_delete=models.CASCADE, related_name='runs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    actual_status_code = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    response_time_ms = models.FloatField(null=True, blank=True)
    error = models.TextField(blank=True)
    passed = models.BooleanField(default=False)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        result = "✓" if self.passed else "✗"
        return f"{result} APITestRun {self.id} for {self.api_test_case.title}"