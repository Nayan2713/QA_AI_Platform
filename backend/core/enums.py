# backend/core/enums.py

"""Centralised enum/choice definitions for the QA AI Platform.

Import these in models instead of defining inline choice lists so that
values stay in sync across the codebase and IDE autocompletion works.
"""

from django.db import models


# ── Application ──────────────────────────────────────────────

class ApplicationStatus(models.TextChoices):
    IDLE = "IDLE", "Idle"
    DISCOVERING = "DISCOVERING", "Discovering"
    DISCOVERED = "DISCOVERED", "Discovered"
    FAILED = "FAILED", "Failed"


class LoginStatus(models.TextChoices):
    NOT_ATTEMPTED = "NOT_ATTEMPTED", "Not Attempted"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"


# ── TestCase ─────────────────────────────────────────────────

class TestCaseValidationStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    VERIFIED = "VERIFIED", "Verified"
    BROKEN = "BROKEN", "Broken"


# ── TestRun ──────────────────────────────────────────────────

class TestRunStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


# ── TestResult ───────────────────────────────────────────────

class TestResultStatus(models.TextChoices):
    PASSED = "PASSED", "Passed"
    FAILED = "FAILED", "Failed"


# ── Bug ──────────────────────────────────────────────────────

class BugSeverity(models.TextChoices):
    CRITICAL = "critical", "Critical"
    HIGH = "high", "High"
    MEDIUM = "medium", "Medium"
    LOW = "low", "Low"


# ── CeleryTask ───────────────────────────────────────────────

class CeleryTaskStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROGRESS = "progress", "In Progress"
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"


# ── TestValidation ───────────────────────────────────────────

class TestValidationStatus(models.TextChoices):
    HIGHLY_RELEVANT = "HIGHLY_RELEVANT", "Highly Relevant (90-100%)"
    RELEVANT = "RELEVANT", "Relevant (70-89%)"
    SOMEWHAT_RELEVANT = "SOMEWHAT_RELEVANT", "Somewhat Relevant (50-69%)"
    IRRELEVANT = "IRRELEVANT", "Irrelevant (<50%)"


# ── FlakinessReport ──────────────────────────────────────────

class FlakinessStatus(models.TextChoices):
    STABLE = "STABLE", "Stable (0-10% failure)"
    MOSTLY_STABLE = "MOSTLY_STABLE", "Mostly Stable (10-20% failure)"
    FLAKY = "FLAKY", "Flaky (20-50% failure)"
    VERY_FLAKY = "VERY_FLAKY", "Very Flaky (>50% failure)"


# ── BugValidation ────────────────────────────────────────────

class VerificationStatus(models.TextChoices):
    VERIFIED = "VERIFIED", "Real Bug"
    FALSE_POSITIVE = "FALSE_POSITIVE", "False Positive"
    NEEDS_REVIEW = "NEEDS_REVIEW", "Needs Manual Review"


# ── QualityMetrics ───────────────────────────────────────────

class QualityGrade(models.TextChoices):
    A = "A", "Excellent (90-100)"
    B = "B", "Good (80-89)"
    C = "C", "Fair (70-79)"
    D = "D", "Poor (60-69)"
    F = "F", "Failing (<60)"
