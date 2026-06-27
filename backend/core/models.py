from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
import base64
from cryptography.fernet import Fernet


def _get_fernet():
    """Return a Fernet cipher keyed from the first 32 URL-safe base64 bytes of SECRET_KEY."""
    key_bytes = settings.SECRET_KEY.encode()[:32]
    # Fernet needs exactly 32 bytes encoded as URL-safe base64
    fernet_key = base64.urlsafe_b64encode(key_bytes.ljust(32, b'=')[:32])
    return Fernet(fernet_key)


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
    STATUS_CHOICES = [
        ('IDLE', 'Idle'),
        ('DISCOVERING', 'Discovering'),
        ('DISCOVERED', 'Discovered'),
        ('FAILED', 'Failed'),
    ]
    
    LOGIN_STATUS_CHOICES = [
        ('NOT_ATTEMPTED', 'Not Attempted'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
    url = models.URLField(max_length=500)
    base_url = models.URLField(max_length=500)
    login_url = models.URLField(max_length=500, blank=True, null=True)
    username = models.CharField(max_length=255, blank=True, null=True)
    # FIX: store the target-site password encrypted at rest
    password = EncryptedCharField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IDLE')
    discovery_source = models.CharField(max_length=20, blank=True, null=True) # 'mcp' or 'browser'
    login_status = models.CharField(max_length=20, choices=LOGIN_STATUS_CHOICES, default='NOT_ATTEMPTED')
    storage_state = models.TextField(blank=True, null=True)
    login_error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.url} ({self.user.username})"


class Page(models.Model):
    app = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='pages')
    url = models.URLField(max_length=1000)
    title = models.CharField(max_length=500, blank=True, null=True)
    forms = models.JSONField(default=list)  # [{"id": "...", "fields": [...], "action": "...", "method": "..."}]
    buttons = models.JSONField(default=list)  # [{"text": "...", "selector": "..."}]
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title or self.url} in {self.app.url}"


class TestCase(models.Model):
    app = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='test_cases')
    title = models.CharField(max_length=255)
    steps = models.JSONField(default=list)  # [{"action": "...", "selector": "...", "value": "..."}]
    expected_result = models.TextField()
    ai_generated = models.BooleanField(default=True)
    validation_status = models.CharField(
        max_length=20,
        choices=[
            ('DRAFT', 'Draft'),
            ('VERIFIED', 'Verified'),
            ('BROKEN', 'Broken')
        ],
        default='DRAFT'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.app.url}"


class TestRun(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('RUNNING', 'Running'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    test_case = models.ForeignKey(TestCase, on_delete=models.CASCADE, related_name='test_runs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    metadata = models.JSONField(default=dict, blank=True)
    bugs_found = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Run {self.id} for {self.test_case.title} ({self.status})"


class TestResult(models.Model):
    STATUS_CHOICES = [
        ('PASSED', 'Passed'),
        ('FAILED', 'Failed'),
    ]
    test_run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='step_results')
    step_number = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
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
    SEVERITY_CHOICES = [
        ('critical', 'Critical'),
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]
    test_run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='bugs')
    title = models.CharField(max_length=255)
    description = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    api_endpoint = models.ForeignKey(APIEndpoint, on_delete=models.SET_NULL, blank=True, null=True, related_name='bugs')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.severity.upper()}] {self.title}"

class CeleryTask(models.Model):
    """Track all celery tasks"""
    TASK_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('progress', 'In Progress'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]
    
    task_id = models.CharField(max_length=255, unique=True)
    task_type = models.CharField(max_length=100)  # 'discovery', 'test_gen', etc
    status = models.CharField(max_length=20, choices=TASK_STATUS_CHOICES)
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
        choices=[
            ('HIGHLY_RELEVANT', 'Highly Relevant (90-100%)'),
            ('RELEVANT', 'Relevant (70-89%)'),
            ('SOMEWHAT_RELEVANT', 'Somewhat Relevant (50-69%)'),
            ('IRRELEVANT', 'Irrelevant (<50%)')
        ],
        default='IRRELEVANT'
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
        choices=[
            ('STABLE', 'Stable (0-10% failure)'),
            ('MOSTLY_STABLE', 'Mostly Stable (10-20% failure)'),
            ('FLAKY', 'Flaky (20-50% failure)'),
            ('VERY_FLAKY', 'Very Flaky (>50% failure)')
        ],
        default='VERY_FLAKY'
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
        choices=[
            ('VERIFIED', 'Real Bug'),
            ('FALSE_POSITIVE', 'False Positive'),
            ('NEEDS_REVIEW', 'Needs Manual Review')
        ],
        default='NEEDS_REVIEW'
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
        choices=[
            ('A', 'Excellent (90-100)'),
            ('B', 'Good (80-89)'),
            ('C', 'Fair (70-79)'),
            ('D', 'Poor (60-69)'),
            ('F', 'Failing (<60)')
        ],
        default='F'
    )
    recommendations = models.JSONField(default=list)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_updated']

    def __str__(self):
        app_url = self.application.url if self.application else 'N/A'
        return f"QualityMetrics for {app_url} — grade {self.grade}"


# from django.db import models
# from django.contrib.auth.models import User

# class Application(models.Model):
#     STATUS_CHOICES = [
#         ('IDLE', 'Idle'),
#         ('DISCOVERING', 'Discovering'),
#         ('DISCOVERED', 'Discovered'),
#         ('FAILED', 'Failed'),
#     ]
    
#     LOGIN_STATUS_CHOICES = [
#         ('NOT_ATTEMPTED', 'Not Attempted'),
#         ('SUCCESS', 'Success'),
#         ('FAILED', 'Failed'),
#     ]
    
#     user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
#     url = models.URLField(max_length=500)
#     base_url = models.URLField(max_length=500)
#     login_url = models.URLField(max_length=500, blank=True, null=True)
#     username = models.CharField(max_length=255, blank=True, null=True)
#     password = models.CharField(max_length=255, blank=True, null=True)
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IDLE')
#     discovery_source = models.CharField(max_length=20, blank=True, null=True) # 'mcp' or 'browser'
#     login_status = models.CharField(max_length=20, choices=LOGIN_STATUS_CHOICES, default='NOT_ATTEMPTED')
#     storage_state = models.TextField(blank=True, null=True)
#     login_error = models.TextField(blank=True, null=True)
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.url} ({self.user.username})"


# class Page(models.Model):
#     app = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='pages')
#     url = models.URLField(max_length=1000)
#     title = models.CharField(max_length=500, blank=True, null=True)
#     forms = models.JSONField(default=list)  # [{"id": "...", "fields": [...], "action": "...", "method": "..."}]
#     buttons = models.JSONField(default=list)  # [{"text": "...", "selector": "..."}]
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.title or self.url} in {self.app.url}"


# class TestCase(models.Model):
#     app = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='test_cases')
#     title = models.CharField(max_length=255)
#     steps = models.JSONField(default=list)  # [{"action": "...", "selector": "...", "value": "..."}]
#     expected_result = models.TextField()
#     ai_generated = models.BooleanField(default=True)
#     validation_status = models.CharField(
#         max_length=20,
#         choices=[
#             ('DRAFT', 'Draft'),
#             ('VERIFIED', 'Verified'),
#             ('BROKEN', 'Broken')
#         ],
#         default='DRAFT'
#     )
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.title} - {self.app.url}"


# class TestRun(models.Model):
#     STATUS_CHOICES = [
#         ('PENDING', 'Pending'),
#         ('RUNNING', 'Running'),
#         ('COMPLETED', 'Completed'),
#         ('FAILED', 'Failed'),
#     ]
#     test_case = models.ForeignKey(TestCase, on_delete=models.CASCADE, related_name='test_runs')
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
#     metadata = models.JSONField(default=dict, blank=True)
#     bugs_found = models.IntegerField(default=0)
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"Run {self.id} for {self.test_case.title} ({self.status})"


# class TestResult(models.Model):
#     STATUS_CHOICES = [
#         ('PASSED', 'Passed'),
#         ('FAILED', 'Failed'),
#     ]
#     test_run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='step_results')
#     step_number = models.IntegerField()
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES)
#     error = models.TextField(blank=True, null=True)
#     screenshot = models.TextField(blank=True, null=True)  # base64 encoded image
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"Result Step {self.step_number} in Run {self.test_run.id} ({self.status})"


# class APIEndpoint(models.Model):
#     application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='api_endpoints')
#     method = models.CharField(max_length=10)
#     url_pattern = models.CharField(max_length=1000)
#     request_schema = models.JSONField(default=dict, blank=True)
#     response_schema = models.JSONField(default=dict, blank=True)
#     auth_type = models.CharField(max_length=100, blank=True, null=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         unique_together = ('application', 'method', 'url_pattern')
#         ordering = ['url_pattern']

#     def __str__(self):
#         return f"[{self.method}] {self.url_pattern}"


# class Bug(models.Model):
#     SEVERITY_CHOICES = [
#         ('critical', 'Critical'),
#         ('high', 'High'),
#         ('medium', 'Medium'),
#         ('low', 'Low'),
#     ]
#     test_run = models.ForeignKey(TestRun, on_delete=models.CASCADE, related_name='bugs')
#     title = models.CharField(max_length=255)
#     description = models.TextField()
#     severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
#     api_endpoint = models.ForeignKey(APIEndpoint, on_delete=models.SET_NULL, blank=True, null=True, related_name='bugs')
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"[{self.severity.upper()}] {self.title}"

# class CeleryTask(models.Model):
#     """Track all celery tasks"""
#     TASK_STATUS_CHOICES = [
#         ('pending', 'Pending'),
#         ('progress', 'In Progress'),
#         ('success', 'Success'),
#         ('failed', 'Failed'),
#     ]
    
#     task_id = models.CharField(max_length=255, unique=True)
#     task_type = models.CharField(max_length=100)  # 'discovery', 'test_gen', etc
#     status = models.CharField(max_length=20, choices=TASK_STATUS_CHOICES)
#     progress = models.IntegerField(default=0)  # 0-100
#     result = models.JSONField(default=dict, blank=True)
#     error = models.TextField(blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
#     completed_at = models.DateTimeField(null=True, blank=True)
    
#     def __str__(self):
#         return f"{self.task_type} - {self.task_id}"
    
# # backend/qa_engine/models.py
# # ADD THESE MODELS TO YOUR EXISTING models.py

# from django.db import models
# from django.contrib.auth.models import User
# from django.utils import timezone

# # EXISTING MODELS (keep these):
# # - User
# # - Application
# # - Page
# # - TestCase
# # - TestRun
# # - TestResult
# # - Bug

# # NEW QUALITY VALIDATION MODELS
# # backend/core/models.py

# # Find these models and UPDATE them:

# class TestValidation(models.Model):
#     test_case = models.OneToOneField(TestCase, on_delete=models.CASCADE, related_name='quality_validation')
#     application = models.ForeignKey(
#         Application,
#         on_delete=models.CASCADE,
#         related_name='test_validations',
#         null=True,      # ADD THIS
#         blank=True      # ADD THIS
#     )
#     relevance_score = models.FloatField(default=0)
#     elements_found = models.IntegerField(default=0)
#     elements_total = models.IntegerField(default=0)
#     status = models.CharField(
#         max_length=20,
#         choices=[
#             ('HIGHLY_RELEVANT', 'Highly Relevant (90-100%)'),
#             ('RELEVANT', 'Relevant (70-89%)'),
#             ('SOMEWHAT_RELEVANT', 'Somewhat Relevant (50-69%)'),
#             ('IRRELEVANT', 'Irrelevant (<50%)')
#         ],
#         default='IRRELEVANT'
#     )
#     validation_details = models.JSONField(default=dict)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         ordering = ['-created_at']


# class CoverageReport(models.Model):
#     application = models.ForeignKey(
#         Application,
#         on_delete=models.CASCADE,
#         related_name='coverage_reports',
#         null=True,      # ADD THIS
#         blank=True      # ADD THIS
#     )
#     page_coverage = models.FloatField(default=0)
#     form_coverage = models.FloatField(default=0)
#     workflow_coverage = models.FloatField(default=0)
#     overall_coverage = models.FloatField(default=0)
#     total_pages = models.IntegerField(default=0)
#     tested_pages = models.IntegerField(default=0)
#     total_forms = models.IntegerField(default=0)
#     tested_forms = models.IntegerField(default=0)
#     total_workflows = models.IntegerField(default=0)
#     tested_workflows = models.IntegerField(default=0)
#     untested_elements = models.JSONField(default=list)
#     created_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         ordering = ['-created_at']


# class FlakinessReport(models.Model):
#     test_case = models.ForeignKey(
#         TestCase,
#         on_delete=models.CASCADE,
#         related_name='flakiness_reports',
#         null=True,      # ADD THIS
#         blank=True      # ADD THIS
#     )
#     application = models.ForeignKey(
#         Application,
#         on_delete=models.CASCADE,
#         related_name='flakiness_reports',
#         null=True,      # ADD THIS
#         blank=True      # ADD THIS
#     )
#     runs_executed = models.IntegerField(default=5)
#     runs_passed = models.IntegerField(default=0)
#     runs_failed = models.IntegerField(default=0)
#     flakiness_percentage = models.FloatField(default=0)
#     status = models.CharField(
#         max_length=20,
#         choices=[
#             ('STABLE', 'Stable (0-10% failure)'),
#             ('MOSTLY_STABLE', 'Mostly Stable (10-20% failure)'),
#             ('FLAKY', 'Flaky (20-50% failure)'),
#             ('VERY_FLAKY', 'Very Flaky (>50% failure)')
#         ],
#         default='VERY_FLAKY'
#     )
#     failure_patterns = models.JSONField(default=dict)
#     failure_reason = models.TextField(blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     last_run = models.DateTimeField(null=True, blank=True)

#     class Meta:
#         ordering = ['-created_at']


# class BugValidation(models.Model):
#     bug = models.OneToOneField(
#         Bug,
#         on_delete=models.CASCADE,
#         related_name='validation',
#         null=True,      # ADD THIS
#         blank=True      # ADD THIS
#     )
#     application = models.ForeignKey(
#         Application,
#         on_delete=models.CASCADE,
#         related_name='bug_validations',
#         null=True,      # ADD THIS
#         blank=True      # ADD THIS
#     )
#     confidence_score = models.FloatField(default=0)
#     is_verified = models.BooleanField(default=False)
#     verification_status = models.CharField(
#         max_length=20,
#         choices=[
#             ('VERIFIED', 'Real Bug'),
#             ('FALSE_POSITIVE', 'False Positive'),
#             ('NEEDS_REVIEW', 'Needs Manual Review')
#         ],
#         default='NEEDS_REVIEW'
#     )
#     reproducibility_count = models.IntegerField(default=1)
#     reproducibility_score = models.FloatField(default=0)
#     severity_score = models.FloatField(default=0)
#     error_type = models.CharField(max_length=50, blank=True)
#     validation_methods = models.JSONField(default=dict)
#     validation_notes = models.TextField(blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         ordering = ['-created_at']


# class QualityMetrics(models.Model):
#     application = models.OneToOneField(
#         Application,
#         on_delete=models.CASCADE,
#         related_name='quality_metrics',
#         null=True,      # ADD THIS
#         blank=True      # ADD THIS
#     )
#     coverage_score = models.FloatField(default=0)
#     reliability_score = models.FloatField(default=0)
#     accuracy_score = models.FloatField(default=0)
#     relevance_score = models.FloatField(default=0)
#     overall_score = models.FloatField(default=0)
#     grade = models.CharField(
#         max_length=1,
#         choices=[
#             ('A', 'Excellent (90-100)'),
#             ('B', 'Good (80-89)'),
#             ('C', 'Fair (70-79)'),
#             ('D', 'Poor (60-69)'),
#             ('F', 'Failing (<60)')
#         ],
#         default='F'
#     )
#     recommendations = models.JSONField(default=list)
#     last_updated = models.DateTimeField(auto_now=True)