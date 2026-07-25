from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth.models import User
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Application, Page, TestCase, TestRun, TestResult, Bug, CeleryTask, APIEndpoint, AgentSession
from .serializers import (
    RegisterSerializer, UserSerializer, ApplicationSerializer, ApplicationListSerializer,
    PageSerializer, TestCaseSerializer, TestCaseListSerializer, TestRunSerializer, TestRunListSerializer,
    TestResultSerializer, BugSerializer, BugDetailSerializer, CeleryTaskSerializer,
    APIEndpointSerializer, AgentSessionSerializer
)
from services.test_validation_service import TestValidationService

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000

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

    def get_serializer_class(self):
        if self.action == 'list':
            return ApplicationListSerializer
        return self.serializer_class

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
            app=app,
            task_id=task_id,
            task_type='discovery',
            status='pending',
            progress=0
        )
        from .signals import register_task_user, register_task_app
        register_task_user(task_id, request.user.id)
        register_task_app(task_id, app.id)
        
        # Trigger Celery Task
        from tasks.discovery import start_discovery
        model_choice = request.data.get('model_choice')
        task = start_discovery.apply_async(args=[app.id, model_choice], task_id=task_id, queue='discovery')
        
        return Response({
            "status": "Discovery started",
            "task_id": task_id,
            "app_status": app.status
        }, status=status.HTTP_202_ACCEPTED)

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
                app=app,
                task_id=task_id,
                task_type='execution',
                status='pending',
                progress=0,
                result={"status_text": f"Starting test execution run for {tc.title}..."}
            )
            from .signals import register_task_user, register_task_app
            register_task_user(task_id, request.user.id)
            register_task_app(task_id, app.id)
            model_choice = request.data.get('model_choice')
            execute_test.apply_async(args=[test_run.id, model_choice], task_id=task_id, queue='execution')
            task_ids.append(task_id)
            test_run_ids.append(test_run.id)
            
        return Response({
            "status": "Test execution runs started",
            "test_run_ids": test_run_ids,
            "task_ids": task_ids
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['post'], url_path='detect-bugs')
    def detect_bugs(self, request, pk=None):
        app = self.get_object()
        import uuid
        task_id = str(uuid.uuid4())
        
        CeleryTask.objects.create(
            app=app,
            task_id=task_id,
            task_type='bug_detection',
            status='pending',
            progress=0,
            result={"status_text": "Initializing agentic bug audit..."}
        )
        from .signals import register_task_user, register_task_app
        register_task_user(task_id, request.user.id)
        register_task_app(task_id, app.id)
        
        from tasks.bug_detection import start_agentic_bug_detection
        task = start_agentic_bug_detection.apply_async(args=[app.id], task_id=task_id, queue='quality')
        
        return Response({
            "status": "Bug detection started",
            "task_id": task_id
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['get'])
    def bugs(self, request, pk=None):
        app = self.get_object()
        from django.db.models import Q
        bugs = (
            Bug.objects.filter(Q(application=app) | Q(test_run__test_case__app=app))
            .select_related('application', 'test_run', 'test_run__test_case', 'test_run__test_case__app')
            .distinct()
            .order_by('-created_at')
        )
        page = self.paginate_queryset(bugs)
        if page is not None:
            serializer = BugSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = BugSerializer(bugs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='api-endpoints')
    def api_endpoints(self, request, pk=None):
        app = self.get_object()
        endpoints = APIEndpoint.objects.filter(application=app).order_by('url_pattern')
        serializer = APIEndpointSerializer(endpoints, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='api-dependency-graph')
    def api_dependency_graph(self, request, pk=None):
        app = self.get_object()
        from services.dependency_mapper import APIDependencyMapper
        graph = APIDependencyMapper.build_dependency_graph(app)
        return Response(graph)

    @action(detail=True, methods=['post'], url_path='stop-all')
    def stop_all(self, request, pk=None):
        """
        Stop ALL pending/running Celery tasks for this application.

        For -P threads workers (Windows), Celery revoke(terminate=True) cannot
        kill threads via SIGKILL. We use cooperative cancellation via Redis
        stop flags — each task calls check_cancelled(task_id) at every step,
        and raises TaskCancelled when the flag is set.
        """
        app = self.get_object()
        from qa_engine.celery import app as celery_app
        from qa_engine.redis_client import get_redis_client
        from tasks.cancellation import set_stop_flag

        stopped_task_ids = []
        errors = []

        try:
            # 1. Fetch active task IDs from SQL database first (robust persistent mapping)
            db_task_ids = list(
                CeleryTask.objects.filter(
                    app=app,
                    status__in=['pending', 'progress']
                ).values_list('task_id', flat=True)
            )

            # 2. Redis scan fallback
            redis_task_ids = []
            try:
                r = get_redis_client()
                cursor = 0
                while True:
                    cursor, keys = r.scan(cursor, match='task_app:*', count=200)
                    for key in keys:
                        val = r.get(key)
                        if val and int(val) == app.id:
                            tid = key.decode().replace('task_app:', '', 1)
                            redis_task_ids.append(tid)
                    if cursor == 0:
                        break
            except Exception as redis_err:
                errors.append(f"Redis registry lookup warning: {str(redis_err)}")

            # Combine unique task IDs
            all_task_ids = list(set(db_task_ids + redis_task_ids))

            for tid in all_task_ids:
                try:
                    # Set cooperative stop flag (works for threads)
                    set_stop_flag(tid)

                    # Try Celery revoke
                    try:
                        celery_app.control.revoke(tid, terminate=True, signal='SIGTERM')
                    except Exception:
                        pass

                    # Mark CeleryTask as failed in DB
                    updated = CeleryTask.objects.filter(
                        task_id=tid,
                        status__in=['pending', 'progress']
                    ).update(status='failed', error='Stopped by user.')
                    stopped_task_ids.append(tid)
                except Exception as e:
                    errors.append(f"{tid}: {str(e)}")

        except Exception as e:
            return Response(
                {"status": "error", "message": f"Failed to stop tasks: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Mark any PENDING/RUNNING TestRuns for this app as FAILED
        try:
            TestRun.objects.filter(
                test_case__app=app,
                status__in=['PENDING', 'RUNNING']
            ).update(status='FAILED')
        except Exception as e:
            errors.append(f"TestRun update failed: {str(e)})")

        # Reset app to IDLE if it was DISCOVERING
        try:
            Application.objects.filter(id=app.id, status='DISCOVERING').update(status='IDLE')
        except Exception as e:
            errors.append(f"App status reset failed: {str(e)}")

        return Response({
            "status": "success",
            "stopped_count": len(stopped_task_ids),
            "errors": errors,
            "message": f"Stop signal sent to {len(stopped_task_ids)} task(s) for this application."
        })



class TestCaseViewSet(viewsets.ModelViewSet):
    serializer_class = TestCaseSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = TestCase.objects.filter(app__user=self.request.user).select_related('app').order_by('-created_at')
        app_id = self.request.query_params.get('app')
        if app_id:
            queryset = queryset.filter(app_id=app_id)
        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return TestCaseListSerializer
        return TestCaseSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx

    def perform_create(self, serializer):
        # Set ai_generated to False by default for manual creation
        ai_generated = self.request.data.get('ai_generated', False)
        # Ensure it is a boolean
        ai_generated = str(ai_generated).lower() in ['true', '1', 't', 'y', 'yes']
        serializer.save(ai_generated=ai_generated)

    @action(detail=False, methods=['post'])
    def generate(self, request):
        app_id = request.data.get('app_id')
        model_choice = request.data.get('model_choice')
        if not app_id:
            return Response({"error": "app_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            app = Application.objects.get(id=app_id, user=request.user)
        except Application.DoesNotExist:
            return Response({"error": "Application not found"}, status=status.HTTP_404_NOT_FOUND)

        import uuid
        task_id = str(uuid.uuid4())
        
        CeleryTask.objects.create(
            app=app,
            task_id=task_id,
            task_type='test_generation',
            status='pending',
            progress=0,
            result={"status_text": "Initializing test generation..."}
        )
        from .signals import register_task_user, register_task_app
        register_task_user(task_id, request.user.id)
        register_task_app(task_id, app.id)

        # Trigger Celery Task
        from tasks.test_generation import generate_tests
        task = generate_tests.apply_async(args=[app.id, model_choice], task_id=task_id, queue='discovery')
        
        return Response({
            "status": "Test case generation started",
            "task_id": task_id
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=['post'], url_path='generate_single')
    def generate_single(self, request):
        app_id = request.data.get('app_id')
        title = request.data.get('title')
        model_choice = request.data.get('model_choice', 'auto')
        
        if not app_id or not title:
            return Response({"error": "app_id and title are required"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            app = Application.objects.get(id=app_id, user=request.user)
        except Application.DoesNotExist:
            return Response({"error": "Application not found"}, status=status.HTTP_404_NOT_FOUND)
            
        from core.models import Page, APIEndpoint
        
        pages = Page.objects.filter(app=app)
        pages_list = [
            {"url": p.url, "title": p.title, "forms": p.forms, "buttons": p.buttons}
            for p in pages
        ]
        
        api_endpoints = APIEndpoint.objects.filter(application=app)
        api_list = [
            {
                "method": api.method,
                "url_pattern": api.url_pattern,
                "request_schema": api.request_schema,
                "response_schema": api.response_schema,
                "auth_type": api.auth_type,
            }
            for api in api_endpoints
        ]
        
        pages_data = {
            "pages": pages_list,
            "api_endpoints": api_list,
            "industry": app.industry
        }
        
        from services.llm_service import LLMService
        llm_service = LLMService(model_choice=model_choice)
        
        test_case_data = llm_service.generate_single_test_case(pages_data, title)
        
        if not test_case_data:
            return Response({"error": "Failed to generate test case"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        from config.llm_config import get_llm
        try:
            llm = get_llm(model_choice=model_choice)
            test_case_data["model_used"] = getattr(llm, 'model', model_choice)
        except Exception:
            test_case_data["model_used"] = model_choice
            
        return Response(test_case_data)

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
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = TestRun.objects.filter(test_case__app__user=self.request.user).select_related('test_case', 'test_case__app')
        
        ids = self.request.query_params.get('ids')
        if ids:
            id_list = [int(x) for x in ids.split(',') if x.isdigit()]
            queryset = queryset.filter(id__in=id_list)
        elif self.action == 'list' and 'page' not in self.request.query_params:
            # Safeguard against MemoryError when retrieving all test runs
            queryset = queryset[:100]

        # Defer loading the large metadata field for list/bulk actions to prevent database OutOfMemory crashes
        if self.action == 'list' or ids:
            queryset = queryset.defer('metadata')

        if self.action == 'retrieve':
            queryset = queryset.prefetch_related('step_results')
        return queryset.order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'list':
            return TestRunListSerializer
        return TestRunSerializer

    @action(detail=False, methods=['post'])
    def execute(self, request):
        test_case_id = request.data.get('test_case_id')
        model_choice = request.data.get('model_choice')
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
            app=test_case.app,
            task_id=task_id,
            task_type='execution',
            status='pending',
            progress=0,
            result={"status_text": "Starting test execution run..."}
        )
        from .signals import register_task_user, register_task_app
        register_task_user(task_id, request.user.id)
        register_task_app(task_id, test_case.app_id)

        # Trigger Celery Task
        from tasks.execution import execute_test
        task = execute_test.apply_async(args=[test_run.id, model_choice], task_id=task_id, queue='execution')
        
        return Response({
            "status": "Execution started",
            "test_run_id": test_run.id,
            "task_id": task_id
        }, status=status.HTTP_202_ACCEPTED)
 
    @action(detail=False, methods=['post'])
    def execute_batch(self, request):
        test_case_ids = request.data.get('test_case_ids', [])
        model_choice = request.data.get('model_choice')
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
                    app=test_case.app,
                    task_id=task_id,
                    task_type='execution',
                    status='pending',
                    progress=0,
                    result={"status_text": "Starting test execution run..."}
                )
                from .signals import register_task_user, register_task_app
                register_task_user(task_id, request.user.id)
                register_task_app(task_id, test_case.app_id)
                
                from tasks.execution import execute_test
                execute_test.apply_async(args=[test_run.id, model_choice], task_id=task_id, queue='execution')
                
                runs.append({
                    "test_run_id": test_run.id,
                    "test_case_id": tc_id,
                    "task_id": task_id
                })
            except TestCase.DoesNotExist:
                continue
        return Response({"runs": runs}, status=status.HTTP_202_ACCEPTED)

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
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        from django.db.models import Q
        queryset = (
            Bug.objects.filter(
                Q(test_run__test_case__app__user=self.request.user) |
                Q(application__user=self.request.user)
            )
            .select_related('application', 'test_run', 'test_run__test_case', 'test_run__test_case__app', 'api_endpoint')
            .order_by('-created_at')
        )
        app_id = self.request.query_params.get('app')
        if app_id:
            queryset = queryset.filter(
                Q(test_run__test_case__app_id=app_id) |
                Q(application_id=app_id)
            )
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        import re
        unique_bugs = []
        seen = set()
        
        for bug in queryset[:500]:
            endpoint_id = bug.api_endpoint_id if bug.api_endpoint_id else 0
            # Deduplicate by the exact title so failures on different steps are kept separate,
            # but identical step failures across different test runs are still grouped.
            app_id = bug.application_id or (bug.test_run.test_case.app_id if bug.test_run and bug.test_run.test_case else None)
            key = (app_id, bug.title, endpoint_id, bug.severity)
            
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
    serializer_class = CeleryTaskSerializer
    permission_classes = (permissions.IsAuthenticated,)
    lookup_field = 'task_id'

    def get_queryset(self):
        """Filter tasks to only those belonging to the current user's applications."""
        from django.db.models import Q
        qs = CeleryTask.objects.filter(
            Q(app__user=self.request.user) | Q(app__isnull=True)
        ).order_by('-created_at')

        app_id_param = self.request.query_params.get('app_id') or self.request.query_params.get('app')
        if app_id_param:
            try:
                qs = qs.filter(app_id=int(app_id_param))
            except ValueError:
                pass
        return qs

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

    @action(detail=True, methods=['get'], url_path='celery-status')
    def celery_status(self, request, task_id=None):
        """
        Get the real-time Celery task status using AsyncResult.
        """
        from celery.result import AsyncResult
        result = AsyncResult(task_id)
        
        response_data = {
            "task_id": task_id,
            "status": result.state,  # PENDING, STARTED, SUCCESS, FAILURE, etc.
            "result": None,
            "error": None
        }
        
        if result.state == 'SUCCESS':
            response_data["result"] = result.result
        elif result.state == 'FAILURE':
            response_data["error"] = str(result.result)
            
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def stop(self, request, task_id=None):
        task = self.get_object()
        
        # 1. Set cooperative stop flag (for thread workers on Windows & Unix)
        from tasks.cancellation import set_stop_flag
        set_stop_flag(task.task_id)

        # 2. Revoke the Celery task (SIGTERM is cross-platform, SIGKILL is POSIX-only)
        from qa_engine.celery import app as celery_app
        try:
            celery_app.control.revoke(task.task_id, terminate=True, signal='SIGTERM')
        except Exception:
            pass
        
        # 3. Update status in database
        task.status = 'failed'
        task.error = "Task stopped by user."
        task.save()
        
        # 3. Handle Application status revert if needed
        if task.task_type == 'discovery':
            # B4 FIX: Only revert the specific application that this task was
            # running for, instead of blindly updating ALL applications.
            from tasks.discovery import start_discovery
            from core.models import Application
            # The task args contain [app_id] — look it up via Celery inspect
            # or fall back to matching the most recent DISCOVERING app for this user.
            try:
                from qa_engine.redis_client import get_redis_client
                r = get_redis_client()
                user_id = r.get(f"task_user:{task.task_id}")
                if user_id:
                    Application.objects.filter(
                        user_id=int(user_id), status='DISCOVERING'
                    ).update(status='IDLE')
            except Exception:
                pass
            
        return Response({
            "status": "success",
            "message": "Task stopped successfully."
        })

class AgentSessionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AgentSessionSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        queryset = AgentSession.objects.filter(application__user=self.request.user).order_by('-created_at')
        app_id = self.request.query_params.get('app')
        if app_id:
            queryset = queryset.filter(application_id=app_id)
        return queryset


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def health_check(request):
    health = {
        'status': 'healthy',
        'database': 'unknown',
        'redis': 'unknown',
        'celery': 'unknown'
    }
    
    # Check Database
    try:
        from django.db import connection
        connection.ensure_connection()
        health['database'] = 'healthy'
    except Exception as e:
        health['database'] = f'unhealthy: {str(e)}'
        health['status'] = 'unhealthy'
        
    # Check Redis
    try:
        from django.conf import settings
        import redis
        redis_url = settings.CELERY_BROKER_URL
        client = redis.from_url(redis_url)
        client.ping()
        health['redis'] = 'healthy'
    except Exception as e:
        health['redis'] = f'unhealthy: {str(e)}'
        health['status'] = 'unhealthy'
        
    # Check Celery
    try:
        from qa_engine.celery import app as celery_app
        inspector = celery_app.control.inspect(timeout=0.15)
        ping_res = inspector.ping() if inspector else None
        if ping_res:
            health['celery'] = 'healthy'
        else:
            health['celery'] = 'unhealthy: no workers found'
    except Exception as e:
        health['celery'] = f'unhealthy: {str(e)}'
        
    http_status = status.HTTP_200_OK if health['status'] == 'healthy' else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(health, status=http_status)

