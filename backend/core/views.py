from rest_framework import viewsets, status, permissions
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth.models import User
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Application, Page, TestCase, TestRun, TestResult, Bug, CeleryTask, APIEndpoint, AgentSession, TeamMember, Notification
from .serializers import (
    RegisterSerializer, UserSerializer, ApplicationSerializer, ApplicationListSerializer,
    PageSerializer, TestCaseSerializer, TestCaseListSerializer, TestRunSerializer, TestRunListSerializer,
    TestResultSerializer, BugSerializer, BugDetailSerializer, CeleryTaskSerializer,
    APIEndpointSerializer, AgentSessionSerializer, TeamMemberSerializer, NotificationSerializer
)
from services.test_validation_service import TestValidationService


from rest_framework.exceptions import PermissionDenied


def get_user_and_team_user_ids(user):
    from .models import TeamMember
    from django.db.models import Q
    if not user or not user.is_authenticated:
        return []
    if getattr(user, 'email', None):
        TeamMember.objects.filter(email__iexact=user.email, member_user__isnull=True).update(
            member_user=user,
            status='active'
        )
    owned_ids = TeamMember.objects.filter(
        Q(member_user=user) | Q(email__iexact=getattr(user, 'email', '')),
        status='active'
    ).values_list('owner_id', flat=True)
    
    member_user_ids = TeamMember.objects.filter(
        owner=user,
        status='active',
        member_user__isnull=False
    ).values_list('member_user_id', flat=True)

    return list(set([user.id] + list(owned_ids) + list(member_user_ids)))


def get_team_role(user, owner):
    """
    Returns the role of `user` relative to resource `owner`:
    - 'owner': if user.id == owner.id
    - 'admin' | 'member' | 'viewer': from active TeamMember record
    - None: if no active team relationship exists
    """
    if not user or not user.is_authenticated:
        return None
    owner_id = owner.id if hasattr(owner, 'id') else owner
    if user.id == owner_id:
        return 'owner'
    from .models import TeamMember
    from django.db.models import Q
    tm = TeamMember.objects.filter(
        Q(member_user=user) | Q(email__iexact=getattr(user, 'email', '')),
        owner_id=owner_id,
        status='active'
    ).first()
    if tm:
        return tm.role
    return None


def check_team_permission(user, owner, action):
    """
    Checks if `user` has permission to perform `action` on a resource owned by `owner`.
    Raises PermissionDenied if forbidden.
    - 'owner' or 'admin': full access (read, create, update, delete)
    - 'member': read, create, update allowed. Delete (destroy) forbidden.
    - 'viewer': read-only. Create, update, delete forbidden.
    """
    role = get_team_role(user, owner)
    if not role:
        raise PermissionDenied("You do not have access to this resource.")

    if action in ['destroy', 'delete']:
        if role not in ['owner', 'admin']:
            raise PermissionDenied("Only resource owners and team admins can delete resources.")
    elif action in ['create', 'update', 'partial_update', 'perform_create', 'perform_update', 'bulk_upload', 'report_ui_bug', 'generate', 'generate_single', 'validate_test', 'auto_fix']:
        if role not in ['owner', 'admin', 'member']:
            raise PermissionDenied("Viewers have read-only access.")

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

    def perform_update(self, serializer):
        check_team_permission(self.request.user, serializer.instance.user, 'update')
        serializer.save()

    def perform_destroy(self, instance):
        check_team_permission(self.request.user, instance.user, 'destroy')
        instance.delete()

    # Helper query order
    def get_queryset(self):
        user_ids = get_user_and_team_user_ids(self.request.user)
        return Application.objects.filter(user_id__in=user_ids).order_by('-created_at')

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
        unique_bugs = []
        seen = set()
        for bug in bugs:
            norm_title = (bug.title or '').strip().lower()
            norm_type = 'ui' if (bug.bug_type or '').lower() in ['ui', 'ui_issue', 'ui_bug', 'visual'] else (bug.bug_type or '').strip().lower()
            key = (app.id, norm_title, norm_type)
            if key not in seen:
                seen.add(key)
                unique_bugs.append(bug)

        page = self.paginate_queryset(unique_bugs)
        if page is not None:
            serializer = BugSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = BugSerializer(unique_bugs, many=True)
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
        from tasks.cancellation import set_stop_flag, revoke_celery_task

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
                    # Set cooperative stop flag and revoke task safely
                    set_stop_flag(tid)
                    revoke_celery_task(tid)

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

    @action(detail=True, methods=['post'], url_path='scan-ui-bugs')
    def scan_ui_bugs(self, request, pk=None):
        app = self.get_object()
        import uuid
        task_id = str(uuid.uuid4())
        CeleryTask.objects.create(
            app=app,
            task_id=task_id,
            task_type='ui_scan',
            status='pending',
            progress=0
        )
        from tasks.bug_detection import scan_ui_bugs as scan_ui_bugs_task
        scan_ui_bugs_task.apply_async(args=[app.id], task_id=task_id)
        return Response({
            "task_id": task_id,
            "status": "pending",
            "message": "Automated UI bug scan started."
        }, status=status.HTTP_202_ACCEPTED)



class TestCaseViewSet(viewsets.ModelViewSet):
    serializer_class = TestCaseSerializer
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user_ids = get_user_and_team_user_ids(self.request.user)
        queryset = TestCase.objects.filter(app__user_id__in=user_ids).select_related('app').order_by('-created_at')
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
        app = serializer.validated_data.get('app')
        if app:
            check_team_permission(self.request.user, app.user, 'create')
        ai_generated = self.request.data.get('ai_generated', False)
        ai_generated = str(ai_generated).lower() in ['true', '1', 't', 'y', 'yes']
        serializer.save(ai_generated=ai_generated)

    def perform_update(self, serializer):
        check_team_permission(self.request.user, serializer.instance.app.user, 'update')
        serializer.save()

    def perform_destroy(self, instance):
        check_team_permission(self.request.user, instance.app.user, 'destroy')
        instance.delete()

    @action(detail=True, methods=['post'], url_path='auto-fix')
    def auto_fix(self, request, pk=None):
        """
        Manually trigger AI Self-Healing & Selector Validation on a test case.
        """
        tc = self.get_object()
        check_team_permission(request.user, tc.app.user, 'auto_fix')

        import uuid
        from tasks.execution import execute_test
        from .signals import register_task_user, register_task_app

        test_run = TestRun.objects.create(test_case=tc, status='PENDING')
        task_id = str(uuid.uuid4())
        CeleryTask.objects.create(
            app=tc.app,
            task_id=task_id,
            task_type='execution',
            status='pending',
            progress=0,
            result={"status_text": f"Starting Self-Healing verification for '{tc.title}'..."}
        )
        register_task_user(task_id, request.user.id)
        register_task_app(task_id, tc.app.id)

        model_choice = request.data.get('model_choice')
        execute_test.apply_async(args=[test_run.id, model_choice], task_id=task_id, queue='execution')

        return Response({
            "status": "Self-Healing run queued",
            "test_run_id": test_run.id,
            "task_id": task_id
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=['post'], url_path='bulk_upload')

    def bulk_upload(self, request):
        app_id = request.data.get('app_id')
        if not app_id:
            return Response({"error": "app_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        user_ids = get_user_and_team_user_ids(request.user)
        try:
            app = Application.objects.get(id=app_id, user_id__in=user_ids)
            check_team_permission(request.user, app.user, 'bulk_upload')
        except Application.DoesNotExist:
            return Response({"error": "Application not found"}, status=status.HTTP_404_NOT_FOUND)

        is_preview = str(request.data.get('preview', 'false')).lower() in ['true', '1', 't', 'yes']
        test_cases_data = request.data.get('test_cases')

        # Direct JSON payload (already-parsed test cases) — this path is
        # already fast (no file parsing), stays synchronous.
        if test_cases_data and isinstance(test_cases_data, list):
            objs_to_create = []
            for item in test_cases_data:
                objs_to_create.append(TestCase(
                    app=app,
                    title=str(item.get('title', 'Imported Test Case'))[:255],
                    category=item.get('category', 'Generic') if item.get('category') in ['Generic', 'Industry Flow', 'Access Control'] else 'Generic',
                    expected_result=str(item.get('expected_result', 'Verification successful')),
                    steps=item.get('steps', []),
                    ai_generated=False,
                    generation_context=item.get('generation_context', {})
                ))
            created = TestCase.objects.bulk_create(objs_to_create)

            return Response({
                "status": "success",
                "message": f"Successfully created {len(created)} test cases.",
                "created_count": len(created),
                "test_cases": TestCaseSerializer(created, many=True).data
            }, status=status.HTTP_201_CREATED)

        # File upload path (CSV/XLSX/PDF) — this is the slow one. Hand it
        # off to Celery instead of parsing inline on the request thread.
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({"error": "No file provided. Upload a .csv, .xlsx, .xls, or .pdf file."}, status=status.HTTP_400_BAD_REQUEST)

        ext = file_obj.name.lower().split('.')[-1]
        if ext not in ['csv', 'xlsx', 'xls', 'pdf']:
            return Response({"error": f"Unsupported file format '.{ext}'. Supported formats: .csv, .xlsx, .xls, .pdf"}, status=status.HTTP_400_BAD_REQUEST)

        model_choice = request.data.get('model_choice', 'auto')
        file_bytes = file_obj.read()

        import uuid
        task_id = str(uuid.uuid4())
        CeleryTask.objects.create(
            app=app,
            task_id=task_id,
            task_type='bulk_upload',
            status='pending',
            progress=0
        )

        from tasks.bulk_upload import process_bulk_upload
        process_bulk_upload.apply_async(
            args=[app.id, file_bytes, file_obj.name, model_choice, is_preview],
            task_id=task_id
        )

        return Response({
            "status": "pending",
            "task_id": task_id,
            "message": "File received — processing in the background."
        }, status=status.HTTP_202_ACCEPTED)
    
    
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

        # Defer loading the large metadata field for list/bulk actions to prevent database OutOfMemory crashes,
        # but keep metadata loaded when querying specific IDs for real-time execution progress polling
        if self.action == 'list' and not ids:
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
        
        user_ids = get_user_and_team_user_ids(request.user)
        try:
            test_case = TestCase.objects.get(id=test_case_id, app__user_id__in=user_ids)
            check_team_permission(request.user, test_case.app.user, 'create')
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
        
        user_ids = get_user_and_team_user_ids(request.user)
        runs = []
        for tc_id in test_case_ids:
            try:
                test_case = TestCase.objects.get(id=tc_id, app__user_id__in=user_ids)
                check_team_permission(request.user, test_case.app.user, 'create')
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
            "self_healed_count": test_run.self_healed_count,
            "data": serializer.data
        })


class BugViewSet(viewsets.ModelViewSet):
    permission_classes = (permissions.IsAuthenticated,)
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user_ids = get_user_and_team_user_ids(self.request.user)
        from django.db.models import Q
        queryset = (
            Bug.objects.filter(
                Q(test_run__test_case__app__user_id__in=user_ids) |
                Q(application__user_id__in=user_ids)
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
        
        bug_type = self.request.query_params.get('bug_type')
        if bug_type:
            if bug_type.lower() == 'ui':
                queryset = queryset.filter(bug_type__in=['ui', 'ui_issue', 'ui_bug', 'visual'])
            else:
                queryset = queryset.filter(bug_type=bug_type)

        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param)

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        import re
        unique_bugs = []
        seen = set()
        
        for bug in queryset[:500]:
            app_id = bug.application_id or (bug.test_run.test_case.app_id if bug.test_run and bug.test_run.test_case else None)
            norm_title = (bug.title or '').strip().lower()
            norm_type = 'ui' if (bug.bug_type or '').lower() in ['ui', 'ui_issue', 'ui_bug', 'visual'] else (bug.bug_type or '').strip().lower()
            key = (app_id, norm_title, norm_type)
            
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

    def perform_create(self, serializer):
        app = serializer.validated_data.get('application') or (serializer.validated_data.get('test_run').test_case.app if serializer.validated_data.get('test_run') else None)
        if app:
            check_team_permission(self.request.user, app.user, 'create')
        serializer.save()

    def perform_update(self, serializer):
        app = serializer.instance.application or (serializer.instance.test_run.test_case.app if serializer.instance.test_run else None)
        if app:
            check_team_permission(self.request.user, app.user, 'update')
        serializer.save()

    def perform_destroy(self, instance):
        app = instance.application or (instance.test_run.test_case.app if instance.test_run else None)
        if app:
            check_team_permission(self.request.user, app.user, 'destroy')
        instance.delete()

    @action(detail=False, methods=['post'], url_path='report-ui-bug')
    def report_ui_bug(self, request):
        app_id = request.data.get('app_id') or request.data.get('application')
        title = request.data.get('title')
        description = request.data.get('description', '')
        severity = request.data.get('severity', 'medium')
        element_selector = request.data.get('element_selector', '')
        screenshot = request.data.get('screenshot', '')
        steps = request.data.get('steps_to_reproduce', [])

        if not app_id or not title:
            return Response({"error": "app_id and title are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Issue 3: Use team user IDs scoping instead of single user check
        try:
            app = Application.objects.get(id=app_id, user_id__in=get_user_and_team_user_ids(request.user))
        except Application.DoesNotExist:
            return Response({"error": "Application not found"}, status=status.HTTP_404_NOT_FOUND)

        # Issue 2: Enforce team role permission
        check_team_permission(request.user, app.user, 'report_ui_bug')

        bug = Bug.objects.create(
            application=app,
            title=title,
            description=description,
            severity=severity,
            bug_type='ui',
            element_selector=element_selector,
            screenshot=screenshot if isinstance(screenshot, str) else None,
            steps_to_reproduce=steps,
            status='open'
        )

        serializer = self.get_serializer(bug)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


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
        from django.utils import timezone
        import datetime

        # Auto-clean stale pending/progress tasks older than 30 minutes
        thirty_mins_ago = timezone.now() - datetime.timedelta(minutes=30)
        CeleryTask.objects.filter(
            status__in=['pending', 'progress'],
            created_at__lt=thirty_mins_ago
        ).update(status='failed', error='Task timed out.')

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

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        val = self.kwargs.get('task_id') or self.kwargs.get('pk')
        if val:
            if str(val).isdigit():
                obj = queryset.filter(id=int(val)).first()
                if obj:
                    return obj
            obj = queryset.filter(task_id=str(val)).first()
            if obj:
                return obj
        from rest_framework.exceptions import NotFound
        raise NotFound(f"Task with ID {val} not found.")

    @action(detail=True, methods=['get'])
    def status(self, request, task_id=None, pk=None):
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
    def celery_status(self, request, task_id=None, pk=None):
        """
        Get the real-time Celery task status using AsyncResult safely.
        """
        tid = task_id or request.parser_context.get('kwargs', {}).get('pk')
        from celery.result import AsyncResult
        try:
            result = AsyncResult(tid)
            task_state = result.state
            res_val = result.result if task_state == 'SUCCESS' else None
            err_val = str(result.result) if task_state == 'FAILURE' else None
        except Exception as e:
            task_state = 'PENDING'
            res_val = None
            err_val = f"Broker unavailable: {e}"

        response_data = {
            "task_id": tid,
            "status": task_state,
            "result": res_val,
            "error": err_val
        }
            
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def stop(self, request, task_id=None, pk=None):
        task = self.get_object()
        target_task_id = task.task_id
        
        # 1. Set cooperative stop flag & revoke Celery task safely
        from tasks.cancellation import set_stop_flag, revoke_celery_task
        set_stop_flag(target_task_id)
        revoke_celery_task(target_task_id)
        
        # 3. Update status in database
        task.status = 'failed'
        task.error = "Task stopped by user."
        task.save()
        
        # 4. Handle Application status revert if needed
        if task.app:
            task.app.status = 'IDLE'
            task.app.save(update_fields=['status'])
            
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


class TeamMemberViewSet(viewsets.ModelViewSet):
    serializer_class = TeamMemberSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        from django.db.models import Q
        user = self.request.user
        return TeamMember.objects.filter(
            Q(owner=user) | Q(member_user=user)
        ).select_related('owner', 'member_user').order_by('-created_at')

    def perform_create(self, serializer):
        email = serializer.validated_data.get('email', '').strip().lower()
        role = serializer.validated_data.get('role', 'member')
        password = (self.request.data.get('password') or '').strip()

        if not email:
            raise serializers.ValidationError({"email": "Email address is required."})

        # 1. Prevent owner from adding themselves
        if self.request.user.email and email == self.request.user.email.lower():
            raise serializers.ValidationError({"email": "You cannot add yourself as a team member (you are the primary team owner)."})

        # 2. Check if a team member with this email already exists for this owner
        if TeamMember.objects.filter(owner=self.request.user, email__iexact=email).exists():
            raise serializers.ValidationError({"email": "This email is already registered as a member of your team."})

        # 3. Check if member_user exists and is already in this team or is owner
        member_user = User.objects.filter(email__iexact=email).first()
        if member_user:
            if member_user.id == self.request.user.id:
                raise serializers.ValidationError({"email": "You cannot add yourself as a team member."})
            if TeamMember.objects.filter(owner=self.request.user, member_user=member_user).exists():
                raise serializers.ValidationError({"email": "This user is already a member of your team."})

        if password:
            if member_user:
                member_user.set_password(password)
                member_user.save()
            else:
                username_base = email.split('@')[0]
                username = username_base
                cnt = 1
                while User.objects.filter(username=username).exists():
                    username = f"{username_base}_{cnt}"
                    cnt += 1

                member_user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password
                )

        status_val = 'active' if member_user else 'pending'

        serializer.save(
            owner=self.request.user,
            member_user=member_user,
            email=email,
            role=role,
            status=status_val
        )

    def perform_update(self, serializer):
        check_team_permission(self.request.user, serializer.instance.owner, 'update')
        serializer.save()

    def perform_destroy(self, instance):
        check_team_permission(self.request.user, instance.owner, 'destroy')
        instance.delete()


class ChatbotQueryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        message = request.data.get('message', '')
        app_id = request.data.get('app_id')
        
        from services.chatbot_service import ChatbotService
        service = ChatbotService()
        result = service.query_assistant(request.user, message, app_id=app_id)
        
        return Response(result, status=status.HTTP_200_OK)


class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notif = self.get_object()
        notif.is_read = True
        notif.save()
        return Response({'status': 'marked as read'})

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'status': 'all marked as read'})

    @action(detail=False, methods=['delete', 'post'])
    def clear_all(self, request):
        Notification.objects.filter(user=request.user).delete()
        return Response({'status': 'all notifications cleared'})


