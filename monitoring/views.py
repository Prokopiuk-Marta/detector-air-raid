from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import ConflictError
from .models import Alert, Incident, PowerOutage, Service
from .serializers import (
    AlertSerializer,
    IncidentSerializer,
    PowerOutageSerializer,
    ServiceSerializer,
)


class StandardPagination(PageNumberPagination):
    page_size = 20


class ServiceListView(APIView):
    def get(self, request):
        services = Service.objects.all()
        serializer = ServiceSerializer(services, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ServiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ServiceDetailView(APIView):
    def get_object(self, slug):
        try:
            return Service.objects.get(slug=slug)
        except Service.DoesNotExist:
            raise NotFound(f"Сервіс '{slug}' не знайдено.")

    def get(self, request, slug):
        service = self.get_object(slug)
        serializer = ServiceSerializer(service)
        return Response(serializer.data)

    def patch(self, request, slug):
        service = self.get_object(slug)
        serializer = ServiceSerializer(service, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

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
        return Response(status=status.HTTP_204_NO_CONTENT)


class PowerOutageListView(APIView):
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

    def post(self, request):
        serializer = PowerOutageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PowerOutageDetailView(APIView):
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
        return Response(status=status.HTTP_204_NO_CONTENT)


class IncidentListView(APIView):
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

    def post(self, request):
        serializer = IncidentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class IncidentDetailView(APIView):
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
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------- Тривоги ----------


class AlertListView(APIView):
    def get(self, request):
        alerts = Alert.objects.all()

        if request.query_params.get("active") == "true":
            alerts = alerts.filter(finished_at__isnull=True)

        paginator = StandardPagination()
        page = paginator.paginate_queryset(alerts, request, view=self)
        serializer = AlertSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


# ---------- Дані для графіка статистики ----------

TIMELINE_DAYS = {1, 7, 30}


class ServiceTimelineView(APIView):
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
