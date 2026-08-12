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


@extend_schema(
    summary="User Profile & Settings",
    description="Fetch or update current logged in user profile details including username, email, and password.",
)
class UserProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_staff": user.is_staff,
            "date_joined": user.date_joined,
        })

    def patch(self, request):
        user = request.user
        data = request.data

        if "username" in data and data["username"]:
            if User.objects.filter(username=data["username"]).exclude(id=user.id).exists():
                return Response({"error": "Username is already taken."}, status=status.HTTP_400_BAD_REQUEST)
            user.username = data["username"]

        if "email" in data and data["email"]:
            if User.objects.filter(email=data["email"]).exclude(id=user.id).exists():
                return Response({"error": "Email is already in use."}, status=status.HTTP_400_BAD_REQUEST)
            user.email = data["email"]

        if "first_name" in data:
            user.first_name = data["first_name"]
        if "last_name" in data:
            user.last_name = data["last_name"]

        if "new_password" in data and data["new_password"]:
            current_password = data.get("current_password")
            if not current_password or not user.check_password(current_password):
                return Response({"error": "Current password is required and must be correct to set a new password."}, status=status.HTTP_400_BAD_REQUEST)
            user.set_password(data["new_password"])

        user.save()

        return Response({
            "message": "Profile updated successfully.",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_staff": user.is_staff,
                "date_joined": user.date_joined,
            }
        })

