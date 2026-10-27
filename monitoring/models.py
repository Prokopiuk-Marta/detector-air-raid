from django.conf import settings
from django.db import models
from django.utils import timezone


class Service(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=50, unique=True)
    url = models.URLField()
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Check(models.Model):
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="checks",
    )
    checked_at = models.DateTimeField(default=timezone.now)
    is_up = models.BooleanField()
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_time_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-checked_at"]
        indexes = [
            models.Index(fields=["service", "checked_at"]),
        ]

    def __str__(self):
        return f"{self.service} {self.checked_at:%Y-%m-%d %H:%M}"


class Alert(models.Model):
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Тривога {self.started_at:%Y-%m-%d %H:%M}"


class PowerOutage(models.Model):
    GROUP_CHOICES = [
        ("1.1", "1.1"),
        ("1.2", "1.2"),
        ("2.1", "2.1"),
        ("2.2", "2.2"),
        ("3.1", "3.1"),
        ("3.2", "3.2"),
        ("4.1", "4.1"),
        ("4.2", "4.2"),
        ("5.1", "5.1"),
        ("5.2", "5.2"),
        ("6.1", "6.1"),
        ("6.2", "6.2"),
    ]

    group = models.CharField(max_length=3, choices=GROUP_CHOICES)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="power_outages",
    )

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "started_at"],
                name="unique_outage_group_start",
            ),
        ]

    def __str__(self):
        return f"Група {self.group}: {self.started_at:%Y-%m-%d %H:%M}"


class Incident(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    started_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    source_url = models.URLField(blank=True)
    services = models.ManyToManyField(Service, related_name="incidents")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return self.title
