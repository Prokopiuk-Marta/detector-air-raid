from drf_spectacular.utils import OpenApiExample, OpenApiResponse, inline_serializer
from rest_framework import serializers

ErrorSerializer = inline_serializer(
    name="Error",
    fields={
        "error": inline_serializer(
            name="ErrorBody",
            fields={
                "status": serializers.IntegerField(),
                "message": serializers.CharField(),
                "details": serializers.DictField(),
            },
        )
    },
)


def error_response(status, description, message, details=None):
    """Відповідь з помилкою в нашому форматі {"error": {...}} з прикладом."""
    return OpenApiResponse(
        response=ErrorSerializer,
        description=description,
        examples=[
            OpenApiExample(
                f"{status}",
                value={
                    "error": {
                        "status": status,
                        "message": message,
                        "details": details or {},
                    }
                },
            )
        ],
    )


def paginated(serializer_class, name):
    """Схема сторінки списку: {"count", "next", "previous", "results": [...]}."""
    return inline_serializer(
        name=name,
        fields={
            "count": serializers.IntegerField(),
            "next": serializers.URLField(allow_null=True),
            "previous": serializers.URLField(allow_null=True),
            "results": serializer_class(many=True),
        },
    )


VALIDATION_400 = error_response(
    400,
    "Некоректні дані: у details перелічено поля з помилками.",
    "Перевірте введені дані.",
    {"group": ['"9.9" is not a valid choice.']},
)

AUTH_401 = error_response(
    401,
    "Немає access-токена, або він недійсний чи прострочений.",
    "Потрібно увійти в акаунт. Передайте access-токен у заголовку "
    "Authorization: Bearer <token>.",
)

ADMIN_403 = error_response(
    403,
    "Користувач увійшов, але не є адміністратором.",
    "Цю дію може виконати лише адміністратор.",
)


def not_found_404(message):
    return error_response(404, "Об'єкт не знайдено.", message)


def conflict_409(message):
    return error_response(409, "Дія конфліктує з наявними даними.", message)
