from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import Incident, PowerOutage, Service


class ServiceSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    response_time_ms = serializers.SerializerMethodField()
    last_checked_at = serializers.SerializerMethodField()
    uptime_7d = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = [
            "id",
            "name",
            "slug",
            "url",
            "description",
            "is_active",
            "status",
            "response_time_ms",
            "last_checked_at",
            "uptime_7d",
        ]

    def get_status(self, obj):
        last_check = obj.checks.first()
        if last_check is None:
            return "unknown"
        return "up" if last_check.is_up else "down"

    def get_response_time_ms(self, obj):
        last_check = obj.checks.first()
        return last_check.response_time_ms if last_check else None

    def get_last_checked_at(self, obj):
        last_check = obj.checks.first()
        return last_check.checked_at if last_check else None

    def get_uptime_7d(self, obj):
        week_ago = timezone.now() - timedelta(days=7)
        checks = obj.checks.filter(checked_at__gte=week_ago)
        total = checks.count()
        if total == 0:
            return None
        up = checks.filter(is_up=True).count()
        return round(up / total * 100, 2)


class PowerOutageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PowerOutage
        fields = ["id", "group", "started_at", "finished_at"]

    def validate(self, data):
        group = data.get("group", getattr(self.instance, "group", None))
        started_at = data.get("started_at", getattr(self.instance, "started_at", None))
        finished_at = data.get(
            "finished_at", getattr(self.instance, "finished_at", None)
        )

        if finished_at <= started_at:
            raise serializers.ValidationError(
                {"finished_at": "Кінець відключення має бути пізніше за початок."}
            )

        overlapping = PowerOutage.objects.filter(
            group=group,
            started_at__lt=finished_at,
            finished_at__gt=started_at,
        )
        if self.instance is not None:
            overlapping = overlapping.exclude(pk=self.instance.pk)

        existing = overlapping.first()
        if existing is not None:
            raise serializers.ValidationError(
                f"Для групи {group} у цей час уже є відключення "
                f"(id {existing.id}). Змініть час або відредагуйте наявний запис."
            )

        return data


class IncidentSerializer(serializers.ModelSerializer):
    services = serializers.SlugRelatedField(
        many=True,
        slug_field="slug",
        queryset=Service.objects.all(),
        allow_empty=False,
    )

    class Meta:
        model = Incident
        fields = [
            "id",
            "title",
            "description",
            "started_at",
            "resolved_at",
            "source_url",
            "services",
        ]

    def validate(self, data):
        started_at = data.get("started_at", getattr(self.instance, "started_at", None))
        resolved_at = data.get(
            "resolved_at", getattr(self.instance, "resolved_at", None)
        )

        if resolved_at is not None and resolved_at < started_at:
            raise serializers.ValidationError(
                {"resolved_at": "Час завершення не може бути раніше за початок."}
            )

        return data
