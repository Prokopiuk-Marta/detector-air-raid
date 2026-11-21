from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotAuthenticated,
    ValidationError,
)
from rest_framework.views import exception_handler
from rest_framework_simplejwt.exceptions import InvalidToken


class ConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Дію неможливо виконати через конфлікт з наявними даними."
    default_code = "conflict"


def auth_error_message(exc):
    if isinstance(exc, NotAuthenticated):
        return (
            "Потрібно увійти в акаунт. Передайте access-токен у заголовку "
            "Authorization: Bearer <token>."
        )
    if isinstance(exc, InvalidToken):
        return (
            "Токен недійсний або прострочений. Оновіть access-токен через "
            "/api/v1/auth/token/refresh/ або увійдіть знову."
        )
    if isinstance(exc, AuthenticationFailed):
        if exc.get_codes() == "no_active_account":
            return "Неправильний логін або пароль."
        return "Не вдалося перевірити користувача. Увійдіть знову."
    return None


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return None

    if isinstance(exc, ValidationError):
        message = "Перевірте введені дані."
        details = response.data
    else:
        message = auth_error_message(exc) or response.data.get(
            "detail", "Сталася помилка."
        )
        details = {}

    response.data = {
        "error": {
            "status": response.status_code,
            "message": message,
            "details": details,
        }
    }
    return response
