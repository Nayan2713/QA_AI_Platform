# backend/api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views_quality import (
    TestValidationViewSet, CoverageReportViewSet, FlakinessReportViewSet,
    BugValidationViewSet, QualityMetricsViewSet, QualityDashboardView
)

router = DefaultRouter()
router.register(r'test-validations', TestValidationViewSet, basename='test-validation')
router.register(r'coverage-reports', CoverageReportViewSet, basename='coverage-report')
router.register(r'flakiness-reports', FlakinessReportViewSet, basename='flakiness-report')
router.register(r'bug-validations', BugValidationViewSet, basename='bug-validation')
router.register(r'quality-metrics', QualityMetricsViewSet, basename='quality-metrics')
router.register(r'quality-dashboard', QualityDashboardView, basename='quality-dashboard')

urlpatterns = [
    path('', include(router.urls)),
]