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
        try:
            return _get_fernet().decrypt(value.encode()).decode()
        except Exception:
            return value  # return as-is if it was never encrypted (migration compatibility)

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
    created_at = models.DateTimeField(auto_now_add=True)

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
    created_at = models.DateTimeField(auto_now_add=True)

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
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Run {self.id} for {self.test_case.title} ({self.status})"


class TestResult(models.Model):
    STATUS_CHOICES = TestResultStatus.choices
    test_run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='step_results')
    step_number = models.IntegerField()
    status = models.CharField(max_length=20, choices=TestResultStatus.choices)
    error = models.TextField(blank=True, null=True)
    screenshot = models.TextField(blank=True, null=True)  # base64 encoded image
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Result Step {self.step_number} in Run {self.test_run.id} ({self.status})"


class APIEndpoint(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='api_endpoints')
    method = models.CharField(max_length=10)
    url_pattern = models.CharField(max_length=1000)
    request_schema = models.JSONField(default=dict, blank=True)
    response_schema = models.JSONField(default=dict, blank=True)
    auth_type = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
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
    created_at = models.DateTimeField(auto_now_add=True)

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
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.task_type.upper()} session for {self.application.url} ({self.status})"

class CeleryTask(models.Model):
    """Track all celery tasks"""
    TASK_STATUS_CHOICES = CeleryTaskStatus.choices
    
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

# Import signals to register receivers
from . import signals

