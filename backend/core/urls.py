from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ApplicationViewSet,
    TestCaseViewSet,
    TestRunViewSet,
    BugViewSet,
    CeleryTaskViewSet,
    APIEndpointViewSet,
    AgentSessionViewSet,
)

router = DefaultRouter()
router.register(r'applications', ApplicationViewSet, basename='application')
router.register(r'test-cases', TestCaseViewSet, basename='testcase')
router.register(r'test-runs', TestRunViewSet, basename='testrun')
router.register(r'bugs', BugViewSet, basename='bug')
router.register(r'tasks', CeleryTaskViewSet, basename='task')
router.register(r'api-endpoints', APIEndpointViewSet, basename='apiendpoint')
router.register(r'agent-sessions', AgentSessionViewSet, basename='agentsession')

urlpatterns = [
    path('quality/', include('api.urls')),
    # ViewSets
    path('', include(router.urls)),
]

