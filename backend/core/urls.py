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
    ChatbotQueryView,
    NotificationViewSet,
)

from .events import RealTimeEventView


from .views_new_features import (
    VisualBaselineViewSet,
    VisualDiffViewSet,
    APITestCaseViewSet,
    APITestRunViewSet,
    RunAPITestsView,
    RunVisualRegressionView,
)

router = DefaultRouter()
router.register(r'applications', ApplicationViewSet, basename='application')
router.register(r'test-cases', TestCaseViewSet, basename='testcase')
router.register(r'test-runs', TestRunViewSet, basename='testrun')
router.register(r'bugs', BugViewSet, basename='bug')
router.register(r'tasks', CeleryTaskViewSet, basename='task')
router.register(r'celery-tasks', CeleryTaskViewSet, basename='celerytask')
router.register(r'api-endpoints', APIEndpointViewSet, basename='apiendpoint')
router.register(r'agent-sessions', AgentSessionViewSet, basename='agentsession')
router.register(r'team', TeamMemberViewSet, basename='teammember')
router.register(r'notifications', NotificationViewSet, basename='notification')

# New feature viewsets
router.register(r'visual-baselines', VisualBaselineViewSet, basename='visual-baseline')
router.register(r'visual-diffs', VisualDiffViewSet, basename='visual-diff')
router.register(r'api-test-cases', APITestCaseViewSet, basename='api-test-case')
router.register(r'api-test-runs', APITestRunViewSet, basename='api-test-run')

urlpatterns = [
    path('health/', health_check, name='health-check'),
    path('events/', RealTimeEventView.as_view(), name='realtime-events'),
    path('chatbot/query/', ChatbotQueryView.as_view(), name='chatbot-query'),
    path('quality/', include('api.urls')),
    # New feature views
    path('applications/<int:app_id>/run-api-tests/', RunAPITestsView.as_view(), name='run-api-tests'),
    path('applications/<int:app_id>/run-visual-regression/', RunVisualRegressionView.as_view(), name='run-visual-regression'),
    # ViewSets
    path('', include(router.urls)),
]


