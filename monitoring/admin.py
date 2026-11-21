from django.contrib import admin
from .models import Alert, Check, Incident, PowerOutage, Service


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "url", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Check)
class CheckAdmin(admin.ModelAdmin):
    list_display = ["service", "checked_at", "is_up", "status_code", "response_time_ms"]
    list_filter = ["service", "is_up"]
    date_hierarchy = "checked_at"


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ["started_at", "finished_at"]
    date_hierarchy = "started_at"


@admin.register(PowerOutage)
class PowerOutageAdmin(admin.ModelAdmin):
    list_display = ["group", "started_at", "finished_at", "created_by"]
    list_filter = ["group"]
    date_hierarchy = "started_at"


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ["title", "started_at", "resolved_at"]
    list_filter = ["services"]
    search_fields = ["title", "description"]
    filter_horizontal = ["services"]
