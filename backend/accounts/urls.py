from django.urls import path
from .views import RegisterView, EmailTokenObtainPairView

from rest_framework_simplejwt.views import (TokenRefreshView,)

urlpatterns = [
    path("register/",RegisterView.as_view()),

    path("login/",EmailTokenObtainPairView.as_view()),

    path("refresh/",TokenRefreshView.as_view()),
]