from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import (
    RegisterView,
    ApplicationViewSet,
    TestCaseViewSet,
    TestRunViewSet,
    BugViewSet,
)

router = DefaultRouter()
router.register(r'auth/register', RegisterView, basename='register')
router.register(r'applications', ApplicationViewSet, basename='application')
router.register(r'test-cases', TestCaseViewSet, basename='testcase')
router.register(r'test-runs', TestRunViewSet, basename='testrun')
router.register(r'bugs', BugViewSet, basename='bug')

urlpatterns = [
    # Auth endpoints
    path('auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # ViewSets
    path('', include(router.urls)),
]
