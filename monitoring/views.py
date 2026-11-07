from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import ConflictError
from .models import Incident, PowerOutage, Service
from .serializers import IncidentSerializer, PowerOutageSerializer, ServiceSerializer


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
