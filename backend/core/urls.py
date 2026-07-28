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
    TeamMemberViewSet,
    health_check,
)
from .events import RealTimeEventView

router = DefaultRouter()
router.register(r'applications', ApplicationViewSet, basename='application')
router.register(r'test-cases', TestCaseViewSet, basename='testcase')
router.register(r'test-runs', TestRunViewSet, basename='testrun')
router.register(r'bugs', BugViewSet, basename='bug')
router.register(r'tasks', CeleryTaskViewSet, basename='task')
router.register(r'api-endpoints', APIEndpointViewSet, basename='apiendpoint')
router.register(r'agent-sessions', AgentSessionViewSet, basename='agentsession')
router.register(r'team', TeamMemberViewSet, basename='teammember')

urlpatterns = [
    path('health/', health_check, name='health-check'),
    path('events/', RealTimeEventView.as_view(), name='realtime-events'),
    path('quality/', include('api.urls')),
    # ViewSets
    path('', include(router.urls)),
]


