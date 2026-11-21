from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .models import Alert, PowerOutage

PERIODS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def percent(part, total):
    if total == 0:
        return None
    return round(part / total * 100, 2)


def summarize(checks):
    up = [check for check in checks if check.is_up]
    times = [
        check.response_time_ms for check in up if check.response_time_ms is not None
    ]
    return {
        "checks": len(checks),
        "uptime_percent": percent(len(up), len(checks)),
        "avg_response_time_ms": round(sum(times) / len(times)) if times else None,
    }


def split_by_spans(checks, spans):
    """Ділить перевірки на ті, що потрапили в один із проміжків, і решту."""
    inside, outside = [], []
    for check in checks:
        if any(start <= check.checked_at < end for start, end in spans):
            inside.append(check)
        else:
            outside.append(check)
    return inside, outside


def compare(checks, spans):
    inside, outside = split_by_spans(checks, spans)
    return {"during": summarize(inside), "without": summarize(outside)}


def alert_spans(period_start, period_end, level=None):
    alerts = Alert.objects.filter(
        Q(started_at__lt=period_end)
        & (Q(finished_at__gt=period_start) | Q(finished_at__isnull=True))
    )
    if level:
        alerts = alerts.filter(alert_level=level)
    return [(alert.started_at, alert.finished_at or period_end) for alert in alerts]


def outage_spans(period_start, period_end, group=None):
    """Проміжки відключень світла (усіх груп або однієї), що перетинаються з періодом."""
    outages = PowerOutage.objects.filter(
        started_at__lt=period_end, finished_at__gt=period_start
    )
    if group:
        outages = outages.filter(group=group)
    return [(outage.started_at, outage.finished_at) for outage in outages]


def by_hour(checks):
    hours = {hour: [] for hour in range(24)}
    for check in checks:
        hours[timezone.localtime(check.checked_at).hour].append(check)
    return [{"hour": hour, **summarize(hours[hour])} for hour in range(24)]


def service_stats(service, period, group=None):
    period_end = timezone.now()
    period_start = period_end - PERIODS[period]

    checks = list(
        service.checks.filter(
            checked_at__gte=period_start, checked_at__lte=period_end
        ).only("checked_at", "is_up", "response_time_ms")
    )

    return {
        "service": {"slug": service.slug, "name": service.name},
        "period": period,
        "from": period_start,
        "to": period_end,
        **summarize(checks),
        "alerts": {
            **compare(checks, alert_spans(period_start, period_end)),
            "by_level": {
                level: summarize(
                    split_by_spans(
                        checks, alert_spans(period_start, period_end, level)
                    )[0]
                )
                for level, _label in Alert.LEVEL_CHOICES
            },
        },
        "outages": {
            "group": group,
            **compare(checks, outage_spans(period_start, period_end, group)),
        },
        "by_hour": by_hour(checks),
    }


def uptime_by_period(service):
    now = timezone.now()
    counts = {}
    for name, length in PERIODS.items():
        since = Q(checked_at__gte=now - length)
        counts[f"total_{name}"] = Count("id", filter=since)
        counts[f"up_{name}"] = Count("id", filter=since & Q(is_up=True))

    result = service.checks.aggregate(**counts)
    return {
        name: percent(result[f"up_{name}"], result[f"total_{name}"]) for name in PERIODS
    }
