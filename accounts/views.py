# campusalert/accounts/views.py
"""
Accounts API views for CampusAlert.

Changes from original:
- LoginView now uses EmailLoginSerializer instead of simplejwt's
  TokenObtainPairView — accepts email + password instead of username + password
- All username references replaced with email in log messages
- DeviceTokenUpdateView accepts POST instead of PATCH to match
  the React Native authRepository which sends POST

Endpoints:
    POST   /api/v1/accounts/register/          — Create new account
    POST   /api/v1/accounts/login/             — Email + password → JWT tokens
    POST   /api/v1/accounts/token/refresh/     — Refresh access token
    POST   /api/v1/accounts/logout/            — Blacklist refresh token
    GET    /api/v1/accounts/me/                — Authenticated user profile
    POST   /api/v1/accounts/device/            — Register/update FCM token
    POST   /api/v1/accounts/password/change/   — Change password
"""

import logging

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    EmailLoginSerializer,
    FCMTokenUpdateSerializer,
    PasswordChangeSerializer,
    UserProfileSerializer,
    UserRegistrationSerializer,
)

User = get_user_model()
logger = logging.getLogger('campusalert.accounts')


class RegisterView(APIView):
    """
    POST /api/v1/accounts/register/

    Creates a new CampusAlert account.

    Validates:
    - Email domain (must be @covenantuniversity.edu.ng or @stu.cu.edu.ng)
    - Password strength and confirmation match

    Auto-detects role from email domain:
    - @stu.cu.edu.ng              → student
    - @covenantuniversity.edu.ng  → staff

    Returns JWT tokens immediately so the user is logged in after registration.
    """

    permission_classes = [AllowAny]

    def post(self, request) -> Response:
        serializer = UserRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Issue JWT tokens so the user is immediately logged in
        refresh = RefreshToken.for_user(user)

        logger.info(
            'Registration successful: %s (role: %s)',
            user.email,
            user.role,
        )

        return Response(
            {
                'user': UserProfileSerializer(user).data,
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """
    POST /api/v1/accounts/login/

    Authenticates a user with their Covenant University email and password.
    Returns JWT access + refresh tokens along with the user profile.

    This saves the React Native app from making a second API call after login.

    Expected payload:
        { "email": "student@stu.cu.edu.ng", "password": "..." }

    Returns:
        {
            "access":  "<jwt_access_token>",
            "refresh": "<jwt_refresh_token>",
            "user":    { ...UserProfile... }
        }

    Error responses:
        400 — Invalid credentials or unverified account
        423 — Account locked by django-axes (too many failed attempts)
    """

    # Login must be accessible without authentication
    permission_classes = [AllowAny]

    def post(self, request) -> Response:
        # EmailLoginSerializer validates email + password and calls authenticate()
        serializer = EmailLoginSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)

        # User is stored on validated_data by the serializer's validate() method
        user = serializer.validated_data['user']

        # Generate JWT token pair for the authenticated user
        refresh = RefreshToken.for_user(user)

        logger.info(
            'Login successful: %s (role: %s)',
            user.email,
            user.role,
        )

        return Response(
            {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserProfileSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    """
    POST /api/v1/accounts/logout/

    Blacklists the provided refresh token so it cannot be reused.
    The access token expires naturally after its configured lifetime.

    Expected payload: { "refresh": "<refresh_token>" }

    The React Native app sends the refresh token stored in SecureStore.
    After this call succeeds, the app clears its local token storage.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        refresh_token = request.data.get('refresh')

        if not refresh_token:
            return Response(
                {'error': True, 'message': 'refresh token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            logger.info('Logout successful: %s', request.user.email)
            return Response(
                {'message': 'Logged out successfully.'},
                status=status.HTTP_200_OK,
            )
        except TokenError:
            # Token already expired or invalid — user is effectively logged out
            return Response(
                {'message': 'Logged out.'},
                status=status.HTTP_200_OK,
            )


class MeView(APIView):
    """
    GET /api/v1/accounts/me/

    Returns the authenticated user's full profile.

    The React Native app calls this after a token refresh to ensure
    the local user state matches the backend.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DeviceTokenUpdateView(APIView):
    """
    POST /api/v1/accounts/device/

    Registers or updates the FCM device push token for the authenticated user.

    The React Native app calls this on every launch (after login) because
    FCM tokens can be rotated by Firebase at any time. Stale tokens cause
    silent delivery failures.

    Expected payload:
        { "registration_id": "<fcm_token>", "type": "android" }

    Note: The React Native authRepository sends 'registration_id' (the
    django-push-notifications field name convention). We map this to
    our User.fcm_token field in the serializer.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        # Map registration_id → fcm_token for our serializer
        # The React Native app sends { registration_id: token, type: 'android' }
        token_value = request.data.get('registration_id') or request.data.get('fcm_token')

        if not token_value:
            return Response(
                {'error': True, 'message': 'registration_id or fcm_token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = FCMTokenUpdateSerializer(
            instance=request.user,
            data={'fcm_token': token_value},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        logger.info(
            'FCM token updated for user: %s',
            request.user.email,
        )
        return Response(
            {'message': 'Device token updated.'},
            status=status.HTTP_200_OK,
        )


class PasswordChangeView(APIView):
    """
    POST /api/v1/accounts/password/change/

    Changes the authenticated user's password.
    Requires the current password for verification.

    Expected payload:
        {
            "current_password": "...",
            "new_password": "...",
            "new_password_confirm": "..."
        }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        serializer = PasswordChangeSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {'message': 'Password changed successfully.'},
            status=status.HTTP_200_OK,
        )


