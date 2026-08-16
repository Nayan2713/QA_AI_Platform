from django.shortcuts import render
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from drf_spectacular.utils import extend_schema
from .serializers import (
    RegisterSerializer,
    EmailTokenObtainPairSerializer,
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
)
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


@extend_schema(
    summary="Change Password",
    description="Change password for current logged-in user by validating current password.",
    request=ChangePasswordSerializer,
)
class ChangePasswordView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        current_password = serializer.validated_data["current_password"]
        new_password = serializer.validated_data["new_password"]

        if not user.check_password(current_password):
            return Response(
                {"error": "Current password is incorrect."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()

        return Response({"message": "Password changed successfully."})


@extend_schema(
    summary="Forgot Password",
    description="Generate a password reset token for a user by providing registered email.",
    request=ForgotPasswordSerializer,
)
class ForgotPasswordView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = ()
    serializer_class = ForgotPasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        user = User.objects.filter(email__iexact=email).first()

        if user:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            return Response({
                "message": "Password reset token generated successfully. Use this token to reset your password.",
                "reset_token": token,
                "uid": uid,
                "email": user.email
            })

        # Generic response to prevent user enumeration
        return Response({
            "message": "If an account with this email exists, a password reset token has been generated.",
        })


@extend_schema(
    summary="Reset Password",
    description="Reset password using a valid reset token and user email.",
    request=ResetPasswordSerializer,
)
class ResetPasswordView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = ()
    serializer_class = ResetPasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]

        user = User.objects.filter(email__iexact=email).first()

        if not user:
            return Response(
                {"error": "User with this email does not exist."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {"error": "Invalid or expired password reset token."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()

        return Response({"message": "Password reset successfully. You can now log in with your new password."})


