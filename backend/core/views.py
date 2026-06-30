from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.contrib.auth.models import User
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Application, Page, TestCase, TestRun, TestResult, Bug, CeleryTask, APIEndpoint, AgentSession
from .serializers import (
    RegisterSerializer, UserSerializer, ApplicationSerializer, 
    PageSerializer, TestCaseSerializer, TestRunSerializer, 
    TestResultSerializer, BugSerializer, BugDetailSerializer, CeleryTaskSerializer,
    APIEndpointSerializer, AgentSessionSerializer
)
from services.test_validation_service import TestValidationService

# Celery task imports - imported inside methods to prevent circular dependency
# or loading issues before Celery is ready.

class RegisterView(viewsets.GenericViewSet):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            "user": UserSerializer(user).data,
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)


class ApplicationViewSet(viewsets.ModelViewSet):
    serializer_class = ApplicationSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    # Helper query order
    def get_queryset(self):
        return Application.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=True, methods=['post'])
    def discover(self, request, pk=None):
        app = self.get_object()
        app.status = 'DISCOVERING'
        app.save()
        
        import uuid
        task_id = str(uuid.uuid4())
        
        CeleryTask.objects.create(
            task_id=task_id,
            task_type='discovery',
            status='pending',
            progress=0
        )
        
        # Trigger Celery Task
        from tasks.discovery import start_discovery
        task = start_discovery.apply_async(args=[app.id], task_id=task_id)
        
        return Response({
            "status": "Discovery started",
            "task_id": task_id,
            "app_status": app.status
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def pages(self, request, pk=None):
        app = self.get_object()
        pages = app.pages.all()
        serializer = PageSerializer(pages, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        app = self.get_object()
        return Response({
            "id": app.id,
            "status": app.status,
            "discovery_source": app.discovery_source,
            "page_count": app.pages.count()
        })

    @action(detail=True, methods=['post'], url_path='run-tests')
    def run_tests(self, request, pk=None):
        app = self.get_object()
        test_cases = app.test_cases.all()
        if not test_cases.exists():
            return Response({"error": "No test cases found for this application."}, status=status.HTTP_400_BAD_REQUEST)
        
        task_ids = []
        test_run_ids = []
        from tasks.execution import execute_test
        import uuid
        
        for tc in test_cases:
            test_run = TestRun.objects.create(test_case=tc, status='PENDING')
            task_id = str(uuid.uuid4())
            CeleryTask.objects.create(
                task_id=task_id,
                task_type='execution',
                status='pending',
                progress=0,
                result={"status_text": f"Starting test execution run for {tc.title}..."}
            )
            execute_test.apply_async(args=[test_run.id], task_id=task_id)
            task_ids.append(task_id)
            test_run_ids.append(test_run.id)
            
        return Response({
            "status": "Test execution runs started",
            "test_run_ids": test_run_ids,
            "task_ids": task_ids
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='detect-bugs')
    def detect_bugs(self, request, pk=None):
        app = self.get_object()
        import uuid
        task_id = str(uuid.uuid4())
        
        CeleryTask.objects.create(
            task_id=task_id,
            task_type='bug_detection',
            status='pending',
            progress=0,
            result={"status_text": "Initializing agentic bug audit..."}
        )
        
        from tasks.bug_detection import start_agentic_bug_detection
        task = start_agentic_bug_detection.apply_async(args=[app.id], task_id=task_id)
        
        return Response({
            "status": "Bug detection started",
            "task_id": task_id
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def bugs(self, request, pk=None):
        app = self.get_object()
        from django.db.models import Q
        bugs = Bug.objects.filter(Q(application=app) | Q(test_run__test_case__app=app)).distinct().order_by('-created_at')
        serializer = BugSerializer(bugs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='api-dependency-graph')
    def api_dependency_graph(self, request, pk=None):
        app = self.get_object()
        from services.dependency_mapper import APIDependencyMapper
        graph = APIDependencyMapper.build_dependency_graph(app)
        return Response(graph)


class TestCaseViewSet(viewsets.ModelViewSet):
    serializer_class = TestCaseSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        queryset = TestCase.objects.filter(app__user=self.request.user).order_by('-created_at')
        app_id = self.request.query_params.get('app')
        if app_id:
            queryset = queryset.filter(app_id=app_id)
        return queryset

    @action(detail=False, methods=['post'])
    def generate(self, request):
        app_id = request.data.get('app_id')
        if not app_id:
            return Response({"error": "app_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            app = Application.objects.get(id=app_id, user=request.user)
        except Application.DoesNotExist:
            return Response({"error": "Application not found"}, status=status.HTTP_404_NOT_FOUND)

        import uuid
        task_id = str(uuid.uuid4())
        
        CeleryTask.objects.create(
            task_id=task_id,
            task_type='test_generation',
            status='pending',
            progress=0,
            result={"status_text": "Initializing test generation..."}
        )

        # Trigger Celery Task
        from tasks.test_generation import generate_tests
        task = generate_tests.apply_async(args=[app.id], task_id=task_id)
        
        return Response({
            "status": "Test case generation started",
            "task_id": task_id
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def validate_test(self, request, pk=None):
        test_case = self.get_object()
        res = TestValidationService.validate_test_case(test_case.id)
        if res.get("success"):
            return Response(res, status=status.HTTP_200_OK)
        return Response(res, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def auto_fix(self, request, pk=None):
        test_case = self.get_object()
        res = TestValidationService.auto_fix_test_case(test_case.id)
        if res.get("success"):
            return Response(res, status=status.HTTP_200_OK)
        return Response(res, status=status.HTTP_400_BAD_REQUEST)


class TestRunViewSet(viewsets.ModelViewSet):
    serializer_class = TestRunSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return TestRun.objects.filter(test_case__app__user=self.request.user).order_by('-created_at')

    @action(detail=False, methods=['post'])
    def execute(self, request):
        test_case_id = request.data.get('test_case_id')
        if not test_case_id:
            return Response({"error": "test_case_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            test_case = TestCase.objects.get(id=test_case_id, app__user=request.user)
        except TestCase.DoesNotExist:
            return Response({"error": "Test case not found"}, status=status.HTTP_404_NOT_FOUND)

        # Create TestRun
        test_run = TestRun.objects.create(
            test_case=test_case,
            status='PENDING'
        )

        import uuid
        task_id = str(uuid.uuid4())
        
        CeleryTask.objects.create(
            task_id=task_id,
            task_type='execution',
            status='pending',
            progress=0,
            result={"status_text": "Starting test execution run..."}
        )

        # Trigger Celery Task
        from tasks.execution import execute_test
        task = execute_test.apply_async(args=[test_run.id], task_id=task_id)
        
        return Response({
            "status": "Execution started",
            "test_run_id": test_run.id,
            "task_id": task_id
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def execute_batch(self, request):
        test_case_ids = request.data.get('test_case_ids', [])
        if not test_case_ids:
            return Response({"error": "test_case_ids is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        runs = []
        for tc_id in test_case_ids:
            try:
                test_case = TestCase.objects.get(id=tc_id, app__user=request.user)
                test_run = TestRun.objects.create(
                    test_case=test_case,
                    status='PENDING'
                )
                
                import uuid
                task_id = str(uuid.uuid4())
                
                CeleryTask.objects.create(
                    task_id=task_id,
                    task_type='execution',
                    status='pending',
                    progress=0,
                    result={"status_text": "Starting test execution run..."}
                )
                
                from tasks.execution import execute_test
                execute_test.apply_async(args=[test_run.id], task_id=task_id)
                
                runs.append({
                    "test_run_id": test_run.id,
                    "test_case_id": tc_id,
                    "task_id": task_id
                })
            except TestCase.DoesNotExist:
                continue
        return Response({"runs": runs}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        test_run = self.get_object()
        serializer = self.get_serializer(test_run)
        return Response({
            "status": test_run.status,
            "bugs_found": test_run.bugs_found,
            "data": serializer.data
        })


class BugViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        queryset = Bug.objects.filter(test_run__test_case__app__user=self.request.user).order_by('-created_at')
        app_id = self.request.query_params.get('app')
        if app_id:
            queryset = queryset.filter(test_run__test_case__app_id=app_id)
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        import re
        unique_bugs = []
        seen = set()
        
        for bug in queryset:
            endpoint_id = bug.api_endpoint_id if bug.api_endpoint_id else 0
            # Group identical failures together by normalizing "Step X Failed"
            norm_title = re.sub(r'Step \d+ Failed', 'Step Failed', bug.title)
            
            app_id = bug.application_id or (bug.test_run.test_case.app_id if bug.test_run and bug.test_run.test_case else None)
            key = (app_id, norm_title, endpoint_id, bug.severity)
            
            if key not in seen:
                seen.add(key)
                unique_bugs.append(bug)
                
        page = self.paginate_queryset(unique_bugs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(unique_bugs, many=True)
        return Response(serializer.data)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return BugDetailSerializer
        return BugSerializer


class APIEndpointViewSet(viewsets.ModelViewSet):
    serializer_class = APIEndpointSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        queryset = APIEndpoint.objects.filter(application__user=self.request.user).order_by('url_pattern')
        app_id = self.request.query_params.get('app')
        if app_id:
            queryset = queryset.filter(application_id=app_id)
        return queryset

    @action(detail=True, methods=['get'])
    def analyze(self, request, pk=None):
        endpoint = self.get_object()
        app = endpoint.application
        
        # 1. Fetch bugs linked to this endpoint
        bugs = endpoint.bugs.all()
        bug_data = []
        for bug in bugs:
            bug_data.append({
                "id": bug.id,
                "title": bug.title,
                "severity": bug.severity,
                "description": bug.description,
                "created_at": bug.created_at
            })
            
        # 2. Scan TestRuns to find test results/calls that hit this endpoint
        from core.models import TestRun
        from tasks.discovery import get_url_pattern
        from services.quality_analyzer import ResponseQualityAnalyzer
        
        runs = TestRun.objects.filter(test_case__app=app)
        
        calls_found = []
        latency_sum = 0
        latency_count = 0
        max_latency = 0
        min_latency = float('inf')
        
        status_failures_count = 0
        content_error_count = 0
        schema_conformance_count = 0
        
        for run in runs:
            if not isinstance(run.metadata, dict):
                continue
            api_calls = run.metadata.get('api_calls', [])
            
            for call in api_calls:
                call_method = call.get('method', '').upper()
                call_url = call.get('url', '')
                
                # Resolve URL to pattern
                try:
                    pat = get_url_pattern(call_url, app.url)
                except Exception:
                    pat = ""
                    
                if call_method == endpoint.method and pat == endpoint.url_pattern:
                    latency = call.get('latency', 0)
                    status_code = call.get('status', 200)
                    body = call.get('body', '')
                    
                    # Latency calculations
                    latency_sum += latency
                    latency_count += 1
                    if latency > max_latency:
                        max_latency = latency
                    if latency < min_latency:
                        min_latency = latency
                        
                    # Status failure check
                    if status_code >= 400:
                        status_failures_count += 1
                        
                    # Scan issues using quality analyzer logic
                    content_err = ResponseQualityAnalyzer.check_content_errors(status_code, body)
                    if content_err:
                        content_error_count += 1
                        
                    conformance_err = ResponseQualityAnalyzer.check_schema_conformance(call, app)
                    if conformance_err:
                        schema_conformance_count += 1
                        
                    calls_found.append({
                        "run_id": run.id,
                        "test_case_title": run.test_case.title,
                        "status": status_code,
                        "latency": latency,
                        "timestamp": run.created_at
                    })
                    
        avg_latency = int(latency_sum / latency_count) if latency_count > 0 else 0
        min_latency = min_latency if min_latency != float('inf') else 0
        
        # Calculate overall health score for this API (0-100)
        health_score = 100
        if latency_count > 0:
            deductions = (
                status_failures_count * 30 +
                content_error_count * 20 +
                schema_conformance_count * 15
            )
            if avg_latency > 1500:
                deductions += min(20, int((avg_latency - 1500) / 100))
            health_score = max(0, 100 - deductions)
            
        analysis = {
            "endpoint_id": endpoint.id,
            "method": endpoint.method,
            "url_pattern": endpoint.url_pattern,
            "health_score": health_score,
            "total_calls_tracked": latency_count,
            "latency": {
                "avg_ms": avg_latency,
                "min_ms": min_latency,
                "max_ms": max_latency
            },
            "failures": {
                "status_errors": status_failures_count,
                "content_errors": content_error_count,
                "schema_violations": schema_conformance_count
            },
            "linked_bugs": bug_data,
            "call_history": calls_found[:15]
        }
        
        return Response(analysis, status=status.HTTP_200_OK)


class CeleryTaskViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CeleryTask.objects.all()
    serializer_class = CeleryTaskSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = 'task_id'

    @action(detail=True, methods=['get'])
    def status(self, request, task_id=None):
        task = self.get_object()
        return Response({
            "task_id": task.task_id,
            "task_type": task.task_type,
            "status": task.status,
            "progress": task.progress,
            "result": task.result,
            "error": task.error
        })

class AgentSessionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AgentSessionSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        queryset = AgentSession.objects.filter(application__user=self.request.user).order_by('-created_at')
        app_id = self.request.query_params.get('app')
        if app_id:
            queryset = queryset.filter(application_id=app_id)
        return queryset
