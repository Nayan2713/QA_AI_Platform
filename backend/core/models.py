from django.db import models
from django.contrib.auth.models import User

class Application(models.Model):
    STATUS_CHOICES = [
        ('IDLE', 'Idle'),
        ('DISCOVERING', 'Discovering'),
        ('DISCOVERED', 'Discovered'),
        ('FAILED', 'Failed'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
    url = models.URLField(max_length=500)
    base_url = models.URLField(max_length=500)
    login_url = models.URLField(max_length=500, blank=True, null=True)
    username = models.CharField(max_length=255, blank=True, null=True)
    password = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IDLE')
    discovery_source = models.CharField(max_length=20, blank=True, null=True) # 'mcp' or 'browser'
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
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.severity.upper()}] {self.title}"
