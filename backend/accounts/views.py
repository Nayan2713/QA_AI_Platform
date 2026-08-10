from django.shortcuts import render
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from drf_spectacular.utils import extend_schema
from .serializers import RegisterSerializer, EmailTokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView


@extend_schema(
    summary="Register new user",
    description="Registers a new user account and returns JWT access and refresh tokens.",
    request=RegisterSerializer,
)
class RegisterView(generics.CreateAPIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
            },
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)


@extend_schema(
    summary="User Login (JWT Token)",
    description="Obtain JWT access and refresh tokens by providing registered email and password.",
)
class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
