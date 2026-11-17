import logging
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotAuthenticated,
    ValidationError,
)
from rest_framework.views import exception_handler
from rest_framework_simplejwt.exceptions import InvalidToken

logger = logging.getLogger(__name__)


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


def who(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return f"{user.username} (id {user.id})"
    return "гість"


def log_client_error(request, status_code, message, details):
    if request is None:
        return
    where = f"{request.method} {request.path} -> {status_code}"
    if status_code == 400:
        logger.info("%s: помилки в полях %s (%s)", where, sorted(details), who(request))
    elif status_code == 404:
        logger.info("%s: %s (%s)", where, message, who(request))
    else:
        logger.warning("%s: %s (%s)", where, message, who(request))


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

    log_client_error(context.get("request"), response.status_code, message, details)

    response.data = {
        "error": {
            "status": response.status_code,
            "message": message,
            "details": details,
        }
    }
    return response
