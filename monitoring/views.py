import logging
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import ConflictError
from .models import Alert, Incident, PowerOutage, PowerReport, Service
from .permissions import IsAdminOrReadOnly
from .schema import (
    ADMIN_403,
    AUTH_401,
    VALIDATION_400,
    conflict_409,
    not_found_404,
    paginated,
)
from .serializers import (
    AlertSerializer,
    IncidentSerializer,
    PowerOutageSerializer,
    PowerReportSerializer,
    ServiceSerializer,
)

logger = logging.getLogger(__name__)


class StandardPagination(PageNumberPagination):
    page_size = 20


SERVICES = ["Сервіси"]
OUTAGES = ["Відключення світла"]
INCIDENTS = ["Інциденти"]
ALERTS = ["Тривоги"]
REPORTS = ["Заявки про світло"]

PAGE_PARAMETER = OpenApiParameter(
    "page", int, description="Номер сторінки (по 20 записів)."
)
ACTIVE_PARAMETER = OpenApiParameter(
    "active", str, enum=["true"], description="Лише ті, що тривають зараз."
)
GROUP_PARAMETER = OpenApiParameter(
    "group",
    str,
    enum=[f"{main}.{sub}" for main in range(1, 7) for sub in (1, 2)],
    description="Група (черга) відключень.",
)


class ServiceListView(APIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = ServiceSerializer

    @extend_schema(
        tags=SERVICES,
        operation_id="services_list",
        summary="Список сервісів",
        description="Доступно всім. Статус і час відповіді — з останньої перевірки.",
        responses={200: ServiceSerializer(many=True)},
    )
    def get(self, request):
        services = Service.objects.all()
        serializer = ServiceSerializer(services, many=True)
        return Response(serializer.data)

    @extend_schema(
        tags=SERVICES,
        summary="Додати сервіс",
        description="Лише для адміністратора.",
        request=ServiceSerializer,
        responses={
            201: ServiceSerializer,
            400: VALIDATION_400,
            401: AUTH_401,
            403: ADMIN_403,
        },
        examples=[
            OpenApiExample(
                "Новий сервіс",
                value={
                    "name": "Укрзалізниця",
                    "slug": "uz",
                    "url": "https://uz.gov.ua",
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        serializer = ServiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = serializer.save()
        logger.info("Адмін %s додав сервіс '%s'", request.user.username, service.slug)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ServiceDetailView(APIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = ServiceSerializer

    def get_object(self, slug):
        try:
            return Service.objects.get(slug=slug)
        except Service.DoesNotExist:
            raise NotFound(f"Сервіс '{slug}' не знайдено.")

    @extend_schema(
        tags=SERVICES,
        summary="Один сервіс",
        responses={
            200: ServiceSerializer,
            404: not_found_404("Сервіс 'netflix' не знайдено."),
        },
    )
    def get(self, request, slug):
        service = self.get_object(slug)
        serializer = ServiceSerializer(service)
        return Response(serializer.data)

    @extend_schema(
        tags=SERVICES,
        summary="Змінити сервіс",
        description="Лише для адміністратора. Можна передати лише поля, які змінюються.",
        request=ServiceSerializer,
        responses={
            200: ServiceSerializer,
            400: VALIDATION_400,
            401: AUTH_401,
            403: ADMIN_403,
            404: not_found_404("Сервіс 'netflix' не знайдено."),
        },
    )
    def patch(self, request, slug):
        service = self.get_object(slug)
        serializer = ServiceSerializer(service, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        logger.info(
            "Адмін %s змінив сервіс '%s': %s",
            request.user.username,
            service.slug,
            sorted(serializer.validated_data),
        )
        return Response(serializer.data)

    @extend_schema(
        tags=SERVICES,
        summary="Видалити сервіс",
        description=(
            "Лише для адміністратора. Сервіс з історією перевірок або згаданий "
            "в інцидентах видалити не можна (409)."
        ),
        responses={
            204: None,
            401: AUTH_401,
            403: ADMIN_403,
            404: not_found_404("Сервіс 'netflix' не знайдено."),
            409: conflict_409(
                "Неможливо видалити сервіс 'Дія': для нього збережено 1240 перевірок. "
                "Щоб зупинити моніторинг, деактивуйте сервіс (is_active: false)."
            ),
        },
    )
    def delete(self, request, slug):
        service = self.get_object(slug)

        checks_count = service.checks.count()
        if checks_count > 0:
            raise ConflictError(
                f"Неможливо видалити сервіс '{service.name}': для нього збережено "
                f"{checks_count} перевірок. Щоб зупинити моніторинг, "
                f"деактивуйте сервіс (is_active: false)."
            )

        incidents_count = service.incidents.count()
        if incidents_count > 0:
            raise ConflictError(
                f"Неможливо видалити сервіс '{service.name}': він згадується "
                f"в інцидентах ({incidents_count}). Спочатку приберіть його "
                f"з цих інцидентів."
            )

        service.delete()
        logger.info("Адмін %s видалив сервіс '%s'", request.user.username, slug)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PowerOutageListView(APIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = PowerOutageSerializer

    @extend_schema(
        tags=OUTAGES,
        operation_id="outages_list",
        summary="Відключення світла",
        parameters=[GROUP_PARAMETER, ACTIVE_PARAMETER, PAGE_PARAMETER],
        responses={200: paginated(PowerOutageSerializer, "PaginatedOutageList")},
    )
    def get(self, request):
        outages = PowerOutage.objects.all()

        group = request.query_params.get("group")
        if group:
            outages = outages.filter(group=group)

        if request.query_params.get("active") == "true":
            now = timezone.now()
            outages = outages.filter(started_at__lte=now, finished_at__gt=now)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(outages, request, view=self)
        serializer = PowerOutageSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=OUTAGES,
        summary="Додати відключення",
        responses={
            201: PowerOutageSerializer,
            400: VALIDATION_400,
            401: AUTH_401,
            403: ADMIN_403,
        },
    )
    def post(self, request):
        serializer = PowerOutageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        outage = serializer.save()
        logger.info(
            "Адмін %s додав відключення id %s (група %s)",
            request.user.username,
            outage.id,
            outage.group,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=OUTAGES)
class PowerOutageDetailView(APIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = PowerOutageSerializer

    def get_object(self, pk):
        try:
            return PowerOutage.objects.get(pk=pk)
        except PowerOutage.DoesNotExist:
            raise NotFound(f"Відключення з id {pk} не знайдено.")

    def get(self, request, pk):
        outage = self.get_object(pk)
        serializer = PowerOutageSerializer(outage)
        return Response(serializer.data)

    def patch(self, request, pk):
        outage = self.get_object(pk)
        serializer = PowerOutageSerializer(outage, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        outage = self.get_object(pk)
        outage.delete()
        logger.info("Адмін %s видалив відключення id %s", request.user.username, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class IncidentListView(APIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = IncidentSerializer

    @extend_schema(
        tags=INCIDENTS,
        operation_id="incidents_list",
        summary="Інциденти",
        parameters=[
            OpenApiParameter("service", str, description="Slug сервісу, напр. diia."),
            ACTIVE_PARAMETER,
            OpenApiParameter("search", str, description="Пошук у назві та описі."),
            PAGE_PARAMETER,
        ],
        responses={200: paginated(IncidentSerializer, "PaginatedIncidentList")},
    )
    def get(self, request):
        incidents = Incident.objects.all()

        service = request.query_params.get("service")
        if service:
            incidents = incidents.filter(services__slug=service)

        if request.query_params.get("active") == "true":
            incidents = incidents.filter(resolved_at__isnull=True)

        search = request.query_params.get("search")
        if search:
            incidents = incidents.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )

        paginator = StandardPagination()
        page = paginator.paginate_queryset(incidents, request, view=self)
        serializer = IncidentSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=INCIDENTS,
        summary="Додати інцидент",
        responses={
            201: IncidentSerializer,
            400: VALIDATION_400,
            401: AUTH_401,
            403: ADMIN_403,
        },
    )
    def post(self, request):
        serializer = IncidentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        incident = serializer.save()
        logger.info("Адмін %s додав інцидент id %s", request.user.username, incident.id)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=INCIDENTS)
class IncidentDetailView(APIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = IncidentSerializer

    def get_object(self, pk):
        try:
            return Incident.objects.get(pk=pk)
        except Incident.DoesNotExist:
            raise NotFound(f"Інцидент з id {pk} не знайдено.")

    def get(self, request, pk):
        incident = self.get_object(pk)
        serializer = IncidentSerializer(incident)
        return Response(serializer.data)

    def patch(self, request, pk):
        incident = self.get_object(pk)
        serializer = IncidentSerializer(incident, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        incident = self.get_object(pk)
        incident.delete()
        logger.info("Адмін %s видалив інцидент id %s", request.user.username, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AlertListView(APIView):
    serializer_class = AlertSerializer

    @extend_schema(
        tags=ALERTS,
        operation_id="alerts_list",
        summary="Повітряні тривоги в Києві",
        parameters=[ACTIVE_PARAMETER, PAGE_PARAMETER],
        responses={200: paginated(AlertSerializer, "PaginatedAlertList")},
    )
    def get(self, request):
        alerts = Alert.objects.all()

        if request.query_params.get("active") == "true":
            alerts = alerts.filter(finished_at__isnull=True)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(alerts, request, view=self)
        serializer = AlertSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


TIMELINE_DAYS = {1, 7, 30}


class ServiceTimelineView(APIView):
    @extend_schema(
        tags=SERVICES,
        summary="Дані для графіка статистики",
        description="Перевірки сервісу, тривоги, відключення й інциденти за період.",
        parameters=[OpenApiParameter("days", int, enum=[1, 7, 30], default=7)],
        responses={
            200: inline_serializer(
                name="ServiceTimeline",
                fields={
                    "service": inline_serializer(
                        name="TimelineService",
                        fields={
                            "slug": serializers.CharField(),
                            "name": serializers.CharField(),
                        },
                    ),
                    "from": serializers.DateTimeField(),
                    "to": serializers.DateTimeField(),
                    "checks": inline_serializer(
                        name="TimelineCheck",
                        fields={
                            "checked_at": serializers.DateTimeField(),
                            "is_up": serializers.BooleanField(),
                            "response_time_ms": serializers.IntegerField(
                                allow_null=True
                            ),
                        },
                        many=True,
                    ),
                    "alerts": AlertSerializer(many=True),
                    "outages": PowerOutageSerializer(many=True),
                    "incidents": IncidentSerializer(many=True),
                },
            ),
            400: VALIDATION_400,
            404: not_found_404("Сервіс 'netflix' не знайдено."),
        },
    )
    def get(self, request, slug):
        try:
            service = Service.objects.get(slug=slug)
        except Service.DoesNotExist:
            raise NotFound(f"Сервіс '{slug}' не знайдено.")

        try:
            days = int(request.query_params.get("days", 7))
        except ValueError:
            days = None
        if days not in TIMELINE_DAYS:
            raise ValidationError({"days": ["Допустимі значення: 1, 7 або 30."]})

        period_end = timezone.now()
        period_start = period_end - timedelta(days=days)

        checks = service.checks.filter(checked_at__gte=period_start).order_by(
            "checked_at"
        )
        overlaps = Q(started_at__lt=period_end) & (
            Q(finished_at__gt=period_start) | Q(finished_at__isnull=True)
        )
        alerts = Alert.objects.filter(overlaps).order_by("started_at")
        outages = PowerOutage.objects.filter(
            started_at__lt=period_end, finished_at__gt=period_start
        ).order_by("started_at")
        incidents = service.incidents.filter(
            Q(started_at__lt=period_end)
            & (Q(resolved_at__gt=period_start) | Q(resolved_at__isnull=True))
        ).order_by("started_at")

        return Response(
            {
                "service": {"slug": service.slug, "name": service.name},
                "from": period_start,
                "to": period_end,
                "checks": [
                    {
                        "checked_at": check.checked_at,
                        "is_up": check.is_up,
                        "response_time_ms": check.response_time_ms,
                    }
                    for check in checks
                ],
                "alerts": AlertSerializer(alerts, many=True).data,
                "outages": PowerOutageSerializer(outages, many=True).data,
                "incidents": IncidentSerializer(incidents, many=True).data,
            }
        )


def reports_for(user):
    """Адмін бачить усі заявки, звичайний користувач — лише свої."""
    reports = PowerReport.objects.select_related("user")
    if user.is_staff:
        return reports
    return reports.filter(user=user)


class PowerReportListView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PowerReportSerializer

    @extend_schema(
        tags=REPORTS,
        operation_id="power_reports_list",
        summary="Мої заявки",
        description=(
            "Потрібен вхід. Звичайний користувач бачить лише власні заявки, "
            "адміністратор — заявки всіх користувачів. Від нових до старих."
        ),
        parameters=[GROUP_PARAMETER, PAGE_PARAMETER],
        responses={
            200: paginated(PowerReportSerializer, "PaginatedPowerReportList"),
            401: AUTH_401,
        },
    )
    def get(self, request):
        reports = reports_for(request.user)

        group = request.query_params.get("group")
        if group:
            reports = reports.filter(group=group)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(reports, request, view=self)
        serializer = PowerReportSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        tags=REPORTS,
        summary="Повідомити «у мене немає світла»",
        description=(
            "Потрібен вхід. Автор заявки береться з токена: поле user у запиті "
            "ігнорується."
        ),
        request=PowerReportSerializer,
        responses={
            201: PowerReportSerializer,
            400: VALIDATION_400,
            401: AUTH_401,
        },
        examples=[
            OpenApiExample(
                "Нова заявка",
                value={"group": "3.1", "comment": "Немає світла з 18:00"},
                request_only=True,
            ),
            OpenApiExample(
                "Створена заявка",
                value={
                    "id": 31,
                    "user": "marta",
                    "group": "3.1",
                    "comment": "Немає світла з 18:00",
                    "created_at": "2026-11-17T18:05:00+02:00",
                },
                response_only=True,
                status_codes=["201"],
            ),
        ],
    )
    def post(self, request):
        serializer = PowerReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = serializer.save(user=request.user)
        logger.info(
            "Нова заявка «немає світла» id %s: група %s, користувач %s",
            report.id,
            report.group,
            request.user.username,
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PowerReportDetailView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PowerReportSerializer

    def get_object(self, request, pk):
        try:
            return reports_for(request.user).get(pk=pk)
        except PowerReport.DoesNotExist:
            raise NotFound("Заявку не знайдено.") from None

    @extend_schema(
        tags=REPORTS,
        summary="Одна заявка",
        description="Чужа заявка для звичайного користувача повертає 404.",
        responses={
            200: PowerReportSerializer,
            401: AUTH_401,
            404: not_found_404("Заявку не знайдено."),
        },
    )
    def get(self, request, pk):
        report = self.get_object(request, pk)
        return Response(PowerReportSerializer(report).data)

    @extend_schema(
        tags=REPORTS,
        summary="Скасувати заявку",
        description="Користувач видаляє свою заявку, адміністратор — будь-яку.",
        responses={
            204: None,
            401: AUTH_401,
            404: not_found_404("Заявку не знайдено."),
        },
    )
    def delete(self, request, pk):
        report = self.get_object(request, pk)
        report.delete()
        logger.info("Користувач %s видалив заявку id %s", request.user.username, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)
