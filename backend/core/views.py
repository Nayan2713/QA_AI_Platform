from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.contrib.auth.models import User
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Application, Page, TestCase, TestRun, TestResult, Bug
from .serializers import (
    RegisterSerializer, UserSerializer, ApplicationSerializer, 
    PageSerializer, TestCaseSerializer, TestRunSerializer, 
    TestResultSerializer, BugSerializer, BugDetailSerializer
)

# Celery task imports - imported inside methods to prevent circular dependency
# or loading issues before Celery is ready.

class RegisterView(viewsets.GenericViewSet):
    permission_classes = (permissions.AllowAny,)
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

    def get_queryset(self):
        return Application.objects.filter(user=self.request.user).order_dict_by_date()

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
        
        # Trigger Celery Task
        from tasks.discovery import start_discovery
        task = start_discovery.delay(app.id)
        
        return Response({
            "status": "Discovery started",
            "task_id": task.id,
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


class TestCaseViewSet(viewsets.ModelViewSet):
    serializer_class = TestCaseSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        return TestCase.objects.filter(app__user=self.request.user).order_by('-created_at')

    @action(detail=False, methods=['post'])
    def generate(self, request):
        app_id = request.data.get('app_id')
        if not app_id:
            return Response({"error": "app_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            app = Application.objects.get(id=app_id, user=request.user)
        except Application.DoesNotExist:
            return Response({"error": "Application not found"}, status=status.HTTP_404_NOT_FOUND)

        # Trigger Celery Task
        from tasks.test_generation import generate_tests
        task = generate_tests.delay(app.id)
        
        return Response({
            "status": "Test case generation started",
            "task_id": task.id
        }, status=status.HTTP_200_OK)


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

        # Trigger Celery Task
        from tasks.execution import execute_test
        task = execute_test.delay(test_run.id)
        
        return Response({
            "status": "Execution started",
            "test_run_id": test_run.id,
            "task_id": task.id
        }, status=status.HTTP_200_OK)

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
        return Bug.objects.filter(test_run__test_case__app__user=self.request.user).order_by('-created_at')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return BugDetailSerializer
        return BugSerializer
