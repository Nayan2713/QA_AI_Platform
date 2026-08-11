"""
core/views_new_features.py

REST API endpoints for Visual Regression and API Testing features.

Register in core/urls.py:
    from .views_new_features import VisualBaselineViewSet, VisualDiffViewSet, APITestCaseViewSet, APITestRunViewSet, RunAPITestsView
    router.register(r'visual-baselines', VisualBaselineViewSet, basename='visual-baseline')
    router.register(r'visual-diffs', VisualDiffViewSet, basename='visual-diff')
    router.register(r'api-test-cases', APITestCaseViewSet, basename='api-test-case')
    router.register(r'api-test-runs', APITestRunViewSet, basename='api-test-run')
    path('applications/<int:app_id>/run-api-tests/', RunAPITestsView.as_view(), name='run-api-tests'),
    path('applications/<int:app_id>/run-visual-regression/', RunVisualRegressionView.as_view(), name='run-visual-regression'),
"""

import logging
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404

from core.models import (
    Application, VisualBaseline, VisualDiff, APITestCase, APITestRun, TestRun
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Serializers (inline for simplicity — move to serializers.py if preferred)
# ─────────────────────────────────────────────────────────────

from rest_framework import serializers


class VisualBaselineSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisualBaseline
        fields = ['id', 'page', 'step_number', 'screenshot_path', 'width', 'height', 'created_at', 'updated_at']


class VisualDiffSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisualDiff
        fields = ['id', 'test_run', 'baseline', 'step_number', 'diff_percentage', 'diff_screenshot_path', 'status', 'created_at']


class APITestCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = APITestCase
        fields = [
            'id', 'application', 'api_endpoint', 'title', 'method', 'url',
            'headers', 'body', 'expected_status', 'expected_body_contains',
            'auth_required', 'ai_generated', 'created_at',
        ]


class APITestRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = APITestRun
        fields = [
            'id', 'api_test_case', 'status', 'actual_status_code',
            'response_body', 'response_time_ms', 'error',
            'passed', 'failure_reason', 'created_at',
        ]


# ─────────────────────────────────────────────────────────────
# ViewSets
# ─────────────────────────────────────────────────────────────

class VisualBaselineViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve visual baselines for an application's pages."""
    serializer_class = VisualBaselineSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = VisualBaseline.objects.select_related('page__app')
        app_id = self.request.query_params.get('app_id')
        if app_id:
            qs = qs.filter(page__app_id=app_id, page__app__user=self.request.user)
        return qs

    @action(detail=True, methods=['delete'])
    def reset(self, request, pk=None):
        """Reset a baseline so the next run creates a fresh one."""
        baseline = self.get_object()
        import os
        from django.conf import settings
        import pathlib
        path = pathlib.Path(settings.MEDIA_ROOT) / baseline.screenshot_path
        if path.exists():
            os.remove(str(path))
        baseline.delete()
        return Response({'detail': 'Baseline reset. Next run will create a new baseline.'})


class VisualDiffViewSet(viewsets.ReadOnlyModelViewSet):
    """List visual diff results for a test run or application."""
    serializer_class = VisualDiffSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = VisualDiff.objects.select_related('test_run', 'baseline')
        test_run_id = self.request.query_params.get('test_run_id')
        app_id = self.request.query_params.get('app_id')
        if test_run_id:
            qs = qs.filter(test_run_id=test_run_id)
        if app_id:
            qs = qs.filter(test_run__test_case__app_id=app_id)
        return qs


class APITestCaseViewSet(viewsets.ModelViewSet):
    """CRUD for API test cases."""
    serializer_class = APITestCaseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = APITestCase.objects.select_related('application', 'api_endpoint')
        app_id = self.request.query_params.get('app_id')
        if app_id:
            qs = qs.filter(application_id=app_id, application__user=self.request.user)
        else:
            qs = qs.filter(application__user=self.request.user)
        return qs

    @action(detail=True, methods=['post'])
    def run(self, request, pk=None):
        """Execute a single API test case immediately."""
        from services.api_test_service import APITestExecutor
        test_case = self.get_object()
        auth_token = request.auth.token.decode() if hasattr(request.auth, 'token') else None
        executor = APITestExecutor(auth_token=auth_token)
        run = executor.run(test_case)
        return Response(APITestRunSerializer(run).data)


class APITestRunViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve API test run results."""
    serializer_class = APITestRunSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = APITestRun.objects.select_related('api_test_case__application')
        app_id = self.request.query_params.get('app_id')
        test_case_id = self.request.query_params.get('api_test_case_id')
        if app_id:
            qs = qs.filter(api_test_case__application_id=app_id,
                           api_test_case__application__user=self.request.user)
        if test_case_id:
            qs = qs.filter(api_test_case_id=test_case_id)
        return qs


# ─────────────────────────────────────────────────────────────
# Action Views
# ─────────────────────────────────────────────────────────────

class RunAPITestsView(APIView):
    """
    POST /api/applications/{app_id}/run-api-tests/

    Body (optional):
    {
        "generate": true,   // re-generate test cases from LLM (default: true)
    }

    Queues the run_api_tests Celery task and returns immediately.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, app_id):
        app = get_object_or_404(Application, id=app_id, user=request.user)
        generate = request.data.get('generate', True)

        # Extract JWT token to pass to the executor for auth-required tests
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        token = auth_header.replace('Bearer ', '').strip() if auth_header else None

        from tasks.visual_and_api_tasks import run_api_tests
        task = run_api_tests.delay(app.id, auth_token=token, generate=generate)

        return Response({
            'detail': 'API test run queued.',
            'task_id': task.id,
            'app_id': app.id,
        }, status=status.HTTP_202_ACCEPTED)


class RunVisualRegressionView(APIView):
    """
    POST /api/applications/{app_id}/run-visual-regression/

    Body:
    {
        "test_run_id": 123   // specific run to compare
    }

    Queues visual comparison for a completed test run.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, app_id):
        app = get_object_or_404(Application, id=app_id, user=request.user)
        test_run_id = request.data.get('test_run_id')

        if test_run_id:
            run_exists = TestRun.objects.filter(id=test_run_id, test_case__app=app).exists()
            if not run_exists:
                return Response({'error': f'Test run {test_run_id} not found for this application.'}, status=400)
        else:
            # Use the most recent completed run if not specified
            latest = TestRun.objects.filter(
                test_case__app=app, status='COMPLETED'
            ).order_by('-created_at').first()
            if not latest:
                # Fall back to any test run for this app
                latest = TestRun.objects.filter(
                    test_case__app=app
                ).order_by('-created_at').first()
            if not latest:
                return Response({
                    'error': 'No test runs found for this application. Please run at least one test case first to capture screenshots for visual regression.'
                }, status=400)
            test_run_id = latest.id

        from tasks.visual_and_api_tasks import run_visual_regression
        task = run_visual_regression.delay(test_run_id)

        return Response({
            'detail': 'Visual regression check queued.',
            'task_id': task.id,
            'test_run_id': test_run_id,
        }, status=status.HTTP_202_ACCEPTED)