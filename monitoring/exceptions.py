from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.views import exception_handler


class ConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Дію неможливо виконати через конфлікт з наявними даними."
    default_code = "conflict"


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return None

    if isinstance(exc, ValidationError):
        message = "Перевірте введені дані."
        details = response.data
    else:
        message = response.data.get("detail", "Сталася помилка.")
        details = {}

    response.data = {
        "error": {
            "status": response.status_code,
            "message": message,
            "details": details,
        }
    }
    return response
