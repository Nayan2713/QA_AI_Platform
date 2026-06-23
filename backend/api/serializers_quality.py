# backend/api/serializers_quality.py

from rest_framework import serializers
from core.models import (
    TestValidation, CoverageReport, FlakinessReport, BugValidation, QualityMetrics
)


class TestValidationSerializer(serializers.ModelSerializer):
    """Serializer for test validation data"""
    class Meta:
        model = TestValidation
        fields = [
            'id', 'test_case', 'application', 'relevance_score', 'elements_found',
            'elements_total', 'status', 'validation_details', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class CoverageReportSerializer(serializers.ModelSerializer):
    """Serializer for coverage reports"""
    class Meta:
        model = CoverageReport
        fields = [
            'id', 'application', 'page_coverage', 'form_coverage',
            'workflow_coverage', 'overall_coverage', 'total_pages',
            'tested_pages', 'total_forms', 'tested_forms', 'total_workflows',
            'tested_workflows', 'untested_elements', 'created_at'
        ]
        read_only_fields = ['created_at']


class FlakinessReportSerializer(serializers.ModelSerializer):
    """Serializer for flakiness reports"""
    class Meta:
        model = FlakinessReport
        fields = [
            'id', 'test_case', 'application', 'runs_executed', 'runs_passed', 'runs_failed',
            'flakiness_percentage', 'status', 'failure_patterns',
            'failure_reason', 'created_at', 'last_run'
        ]
        read_only_fields = ['created_at', 'last_run']


class BugValidationSerializer(serializers.ModelSerializer):
    """Serializer for bug validation"""
    class Meta:
        model = BugValidation
        fields = [
            'id', 'bug', 'application', 'confidence_score', 'is_verified', 'verification_status',
            'reproducibility_count', 'reproducibility_score', 'severity_score',
            'error_type', 'validation_methods', 'validation_notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class QualityMetricsSerializer(serializers.ModelSerializer):
    """Serializer for overall quality metrics"""
    class Meta:
        model = QualityMetrics
        fields = [
            'id', 'application', 'coverage_score', 'reliability_score',
            'accuracy_score', 'relevance_score', 'overall_score', 'grade',
            'recommendations', 'last_updated'
        ]
        read_only_fields = ['last_updated']