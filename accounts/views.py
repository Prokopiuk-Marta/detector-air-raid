import logging

from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from monitoring.schema import AUTH_401, VALIDATION_400, error_response

from .serializers import RegisterSerializer, UserSerializer

logger = logging.getLogger(__name__)

AUTH = ["Автентифікація"]


class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    @extend_schema(
        tags=AUTH,
        summary="Реєстрація",
        description=(
            "Обов'язкові: username, email, password, password_confirm. "
            "Пароль — щонайменше 8 символів, не лише цифри, не схожий на username "
            "чи email. Email має бути унікальним (без урахування регістру)."
        ),
        request=RegisterSerializer,
        responses={201: UserSerializer, 400: VALIDATION_400},
        examples=[
            OpenApiExample(
                "Нова користувачка",
                value={
                    "username": "marta",
                    "email": "marta@example.com",
                    "first_name": "Марта",
                    "password": "Svitlo2026!",
                    "password_confirm": "Svitlo2026!",
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        logger.info("Зареєстровано користувача %s (id %s)", user.username, user.id)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    @extend_schema(
        tags=AUTH,
        summary="Вхід: отримати JWT",
        description=(
            "Повертає access-токен (живе 15 хв) і refresh-токен (1 доба). "
            "Access передають у заголовку Authorization: Bearer <access>."
        ),
        responses={
            200: inline_serializer(
                name="TokenPair",
                fields={
                    "access": serializers.CharField(),
                    "refresh": serializers.CharField(),
                },
            ),
            401: error_response(
                401, "Неправильний логін або пароль.", "Неправильний логін або пароль."
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        logger.info("Успішний вхід: %s", request.data.get("username"))
        return response


class RefreshView(TokenRefreshView):
    @extend_schema(
        tags=AUTH,
        summary="Оновити access-токен",
        description="Приймає refresh-токен і повертає новий access-токен.",
        responses={
            200: inline_serializer(
                name="AccessToken", fields={"access": serializers.CharField()}
            ),
            401: error_response(
                401,
                "Refresh-токен недійсний або прострочений.",
                "Токен недійсний або прострочений. Оновіть access-токен через "
                "/api/v1/auth/token/refresh/ або увійдіть знову.",
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    @extend_schema(
        tags=AUTH,
        summary="Поточний користувач",
        responses={200: UserSerializer, 401: AUTH_401},
    )
    def get(self, request):
        return Response(UserSerializer(request.user).data)
