# backend/api/views_quality.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Avg
from core.models import (
    TestValidation, CoverageReport, FlakinessReport, BugValidation,
    QualityMetrics, Application, TestCase, Bug
)
from .serializers_quality import (
    TestValidationSerializer, CoverageReportSerializer,
    FlakinessReportSerializer, BugValidationSerializer, QualityMetricsSerializer
)
from tasks.quality_check import (
    validate_test_relevance,
    analyze_coverage,
    validate_bug_accuracy,
    detect_flakiness,
    calculate_quality_metrics,
    run_full_quality_check
)


class TestValidationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints for test validation results.
    Shows which tests are relevant to the website.
    """
    queryset = TestValidation.objects.all()
    serializer_class = TestValidationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter by user's applications"""
        return TestValidation.objects.filter(application__user=self.request.user)
    
    @action(detail=False, methods=['post'])
    def validate_test(self, request):
        """Trigger validation for a specific test"""
        test_case_id = request.data.get('test_case_id')
        
        if not test_case_id:
            return Response(
                {'error': 'test_case_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            test_case = TestCase.objects.get(id=test_case_id, app__user=request.user)
            page = test_case.app.pages.first()
            page_url = page.url if page else ''
            task = validate_test_relevance.delay(test_case_id, page_url)
            return Response({
                'test_case_id': test_case_id,
                'task_id': task.id,
                'message': 'Test validation queued',
                'status': 'success'
            })
        except TestCase.DoesNotExist:
            return Response(
                {'error': 'Test case not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class CoverageReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints for coverage reports.
    Shows what % of the website is covered by tests.
    """
    queryset = CoverageReport.objects.all()
    serializer_class = CoverageReportSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter by user's applications"""
        return CoverageReport.objects.filter(application__user=self.request.user)
    
    @action(detail=False, methods=['post'])
    def analyze_app_coverage(self, request):
        """Analyze coverage for an application"""
        app_id = request.data.get('application_id')
        
        if not app_id:
            return Response(
                {'error': 'application_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            app = Application.objects.get(id=app_id, user=request.user)
            task = analyze_coverage.delay(app_id)
            return Response({
                'application_id': app_id,
                'task_id': task.id,
                'application_name': app.url,
                'message': 'Coverage analysis queued',
                'status': 'success'
            })
        except Application.DoesNotExist:
            return Response(
                {'error': 'Application not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class FlakinessReportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints for flakiness reports.
    Shows which tests are unreliable (flaky).
    """
    queryset = FlakinessReport.objects.all()
    serializer_class = FlakinessReportSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter by user's applications"""
        return FlakinessReport.objects.filter(application__user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def flaky_tests(self, request):
        """Get all flaky tests"""
        app_id = request.query_params.get('application_id')
        
        queryset = self.get_queryset()
        if app_id:
            queryset = queryset.filter(application_id=app_id)
        
        # Filter for flaky tests only
        flaky = queryset.filter(status__in=['FLAKY', 'VERY_FLAKY'])
        
        serializer = self.get_serializer(flaky, many=True)
        return Response({
            'count': flaky.count(),
            'flaky_tests': serializer.data
        })
    
    @action(detail=False, methods=['post'])
    def check_flakiness(self, request):
        """Check if a test is flaky"""
        test_id = request.data.get('test_case_id')
        
        if not test_id:
            return Response(
                {'error': 'test_case_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            test_case = TestCase.objects.get(id=test_id, app__user=request.user)
            task = detect_flakiness.delay(test_id, 5)
            return Response({
                'test_case_id': test_id,
                'task_id': task.id,
                'message': 'Flakiness check queued',
                'status': 'success'
            })
        except TestCase.DoesNotExist:
            return Response(
                {'error': 'Test case not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class BugValidationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints for bug validation.
    Shows which detected bugs are real vs false positives.
    """
    queryset = BugValidation.objects.all()
    serializer_class = BugValidationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter by user's applications"""
        return BugValidation.objects.filter(application__user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def false_positives(self, request):
        """Get all false positive bugs"""
        app_id = request.query_params.get('application_id')
        
        queryset = self.get_queryset()
        if app_id:
            queryset = queryset.filter(application_id=app_id)
        
        false_positives = queryset.filter(verification_status='FALSE_POSITIVE')
        
        serializer = self.get_serializer(false_positives, many=True)
        total = queryset.count()
        fp_percentage = (false_positives.count() / total * 100) if total > 0 else 0
        
        return Response({
            'count': false_positives.count(),
            'false_positives': serializer.data,
            'impact': f"{fp_percentage:.1f}% of bugs are false positives"
        })
    
    @action(detail=False, methods=['post'])
    def validate_bug(self, request):
        """Validate if a bug is real"""
        bug_id = request.data.get('bug_id')
        
        if not bug_id:
            return Response(
                {'error': 'bug_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            bug = Bug.objects.get(id=bug_id, test_run__test_case__app__user=request.user)
            task = validate_bug_accuracy.delay(bug_id)
            return Response({
                'bug_id': bug_id,
                'task_id': task.id,
                'message': 'Bug validation queued',
                'status': 'success'
            })
        except Bug.DoesNotExist:
            return Response(
                {'error': 'Bug not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class QualityMetricsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoints for overall quality metrics.
    Comprehensive view of application quality.
    """
    queryset = QualityMetrics.objects.all()
    serializer_class = QualityMetricsSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter by user's applications"""
        return QualityMetrics.objects.filter(application__user=self.request.user)
    
    @action(detail=False, methods=['get'])
    def by_application(self, request):
        """Get metrics for specific application"""
        app_id = request.query_params.get('application_id')
        
        if not app_id:
            return Response(
                {'error': 'application_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            metrics = QualityMetrics.objects.get(application_id=app_id, application__user=request.user)
            serializer = self.get_serializer(metrics)
            
            return Response({
                'application_id': app_id,
                'metrics': serializer.data,
                'summary': {
                    'overall_grade': metrics.grade,
                    'overall_score': metrics.overall_score,
                    'status': 'Good' if metrics.overall_score >= 80 else 'Needs Improvement',
                    'recommendations': metrics.recommendations
                }
            })
        except QualityMetrics.DoesNotExist:
            return Response(
                {'error': 'No quality metrics found for this application'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['post'])
    def calculate_metrics(self, request):
        """Calculate quality metrics for an application"""
        app_id = request.data.get('application_id')
        
        if not app_id:
            return Response(
                {'error': 'application_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            app = Application.objects.get(id=app_id, user=request.user)
            task = calculate_quality_metrics.delay(app_id)
            return Response({
                'application_id': app_id,
                'task_id': task.id,
                'message': 'Quality metrics calculation queued',
                'status': 'success'
            })
        except Application.DoesNotExist:
            return Response(
                {'error': 'Application not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class QualityDashboardView(viewsets.ViewSet):
    """
    Comprehensive quality dashboard with all metrics.
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """Get complete quality dashboard"""
        app_id = request.query_params.get('application_id')
        
        if not app_id:
            return Response(
                {'error': 'application_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            app = Application.objects.get(id=app_id, user=request.user)
            
            # Get all quality data
            quality_metrics = QualityMetrics.objects.filter(application=app).first()
            latest_coverage = CoverageReport.objects.filter(application=app).latest('created_at') if CoverageReport.objects.filter(application=app).exists() else None
            flakiness_reports = FlakinessReport.objects.filter(application=app)
            bug_validations = BugValidation.objects.filter(application=app)
            test_validations = TestValidation.objects.filter(application=app)
            
            # API catalog & health calculations
            from core.models import APIEndpoint, TestRun
            from tasks.discovery import get_url_pattern
            api_endpoints = APIEndpoint.objects.filter(application=app)
            
            # Extract latency from latest successful run metadata
            latest_run = TestRun.objects.filter(
                test_case__app=app,
                status='COMPLETED'
            ).order_by('-created_at').first()
            
            avg_latencies = {}
            if latest_run and isinstance(latest_run.metadata, dict):
                api_calls = latest_run.metadata.get('api_calls', [])
                pattern_latencies = {}
                for call in api_calls:
                    pattern = get_url_pattern(call.get('url', ''), app.url)
                    pattern_latencies.setdefault(pattern, []).append(call.get('latency', 0))
                for pat, lats in pattern_latencies.items():
                    avg_latencies[pat] = sum(lats) / len(lats) if lats else 0
            
            api_list = []
            for api in api_endpoints:
                bug_count = api.bugs.count()
                pat = api.url_pattern
                api_list.append({
                    'id': api.id,
                    'method': api.method,
                    'url_pattern': pat,
                    'bug_count': bug_count,
                    'avg_latency': int(avg_latencies.get(pat, 0)),
                    'auth_type': api.auth_type
                })
            
            dashboard_data = {
                'application_id': app_id,
                'application_name': app.url,
                'overall_quality': {
                    'grade': quality_metrics.grade if quality_metrics else 'F',
                    'score': quality_metrics.overall_score if quality_metrics else 0,
                    'recommendations': quality_metrics.recommendations if quality_metrics else []
                },
                'component_scores': {
                    'coverage': quality_metrics.coverage_score if quality_metrics else 0,
                    'reliability': quality_metrics.reliability_score if quality_metrics else 0,
                    'accuracy': quality_metrics.accuracy_score if quality_metrics else 0,
                    'relevance': quality_metrics.relevance_score if quality_metrics else 0,
                },
                'coverage': {
                    'page_coverage': latest_coverage.page_coverage if latest_coverage else 0,
                    'form_coverage': latest_coverage.form_coverage if latest_coverage else 0,
                    'workflow_coverage': latest_coverage.workflow_coverage if latest_coverage else 0,
                    'overall': latest_coverage.overall_coverage if latest_coverage else 0,
                },
                'reliability': {
                    'total_flaky_tests': flakiness_reports.filter(status__in=['FLAKY', 'VERY_FLAKY']).count(),
                    'total_stable_tests': flakiness_reports.filter(status__in=['STABLE', 'MOSTLY_STABLE']).count(),
                    'avg_flakiness': flakiness_reports.aggregate(Avg('flakiness_percentage'))['flakiness_percentage__avg'] or 0,
                },
                'accuracy': {
                    'verified_bugs': bug_validations.filter(is_verified=True).count(),
                    'false_positives': bug_validations.filter(is_verified=False).count(),
                    'needs_review': bug_validations.filter(verification_status='NEEDS_REVIEW').count(),
                },
                'test_health': {
                    'relevant_tests': test_validations.filter(status='HIGHLY_RELEVANT').count(),
                    'avg_relevance': test_validations.aggregate(Avg('relevance_score'))['relevance_score__avg'] or 0,
                },
                'api_health': {
                    'total_apis': api_endpoints.count(),
                    'endpoints': api_list,
                }
            }
            
            return Response(dashboard_data)
        except Application.DoesNotExist:
            return Response(
                {'error': 'Application not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['post'])
    def run_full_check(self, request):
        """Run complete quality check"""
        app_id = request.data.get('application_id')
        
        if not app_id:
            return Response(
                {'error': 'application_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            app = Application.objects.get(id=app_id, user=request.user)
            
            import uuid
            task_id = str(uuid.uuid4())
            
            from core.models import CeleryTask
            CeleryTask.objects.create(
                task_id=task_id,
                task_type='quality_check',
                status='pending',
                progress=5,
                result={"status_text": "Queuing full quality check..."}
            )
            
            task = run_full_quality_check.apply_async(args=[app_id], task_id=task_id)
            
            return Response({
                'application_id': app_id,
                'task_id': task_id,
                'status': 'queued',
                'message': 'Full quality check started'
            })
        except Application.DoesNotExist:
            return Response(
                {'error': 'Application not found'},
                status=status.HTTP_404_NOT_FOUND
            )