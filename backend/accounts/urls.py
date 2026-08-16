from django.urls import path
from .views import (
    RegisterView,
    EmailTokenObtainPairView,
    UserProfileView,
    ChangePasswordView,
    ForgotPasswordView,
    ResetPasswordView,
)

from rest_framework_simplejwt.views import (TokenRefreshView,)

urlpatterns = [
    path("register/", RegisterView.as_view()),
    path("login/", EmailTokenObtainPairView.as_view()),
    path("refresh/", TokenRefreshView.as_view()),
    path("profile/", UserProfileView.as_view()),
    path("me/", UserProfileView.as_view()),
    path("change-password/", ChangePasswordView.as_view()),
    path("forgot-password/", ForgotPasswordView.as_view()),
    path("reset-password/", ResetPasswordView.as_view()),
]