from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from monitoring.models import Alert, Check, PowerOutage


def stats_url(slug):
    return reverse("service-stats", args=[slug])


def ago(minutes):
    return timezone.now() - timedelta(minutes=minutes)


def add_check(service, minutes_ago, is_up=True, response_time_ms=300):
    return Check.objects.create(
        service=service,
        checked_at=ago(minutes_ago),
        is_up=is_up,
        status_code=200 if is_up else None,
        response_time_ms=response_time_ms if is_up else None,
    )


def test_stats_for_unknown_service_returns_404(api_client):
    response = api_client.get(stats_url("netflix"))

    assert response.status_code == 404
    assert response.data["error"]["message"] == "Сервіс 'netflix' не знайдено."


@pytest.mark.parametrize(
    "params, field",
    [
        ({"period": "1y"}, "period"),
        ({"group": "9.9"}, "group"),
    ],
    ids=["unknown-period", "unknown-group"],
)
def test_invalid_stats_params_return_400(api_client, service, params, field):
    response = api_client.get(stats_url(service.slug), params)

    assert response.status_code == 400
    assert field in response.data["error"]["details"]


def test_stats_without_checks_are_empty(api_client, service):
    response = api_client.get(stats_url(service.slug))

    assert response.status_code == 200
    assert response.data["period"] == "7d"
    assert response.data["checks"] == 0
    assert response.data["uptime_percent"] is None
    assert response.data["avg_response_time_ms"] is None
    assert len(response.data["by_hour"]) == 24


def test_overall_uptime_and_response_time(api_client, service):
    add_check(service, 30, response_time_ms=200)
    add_check(service, 20, response_time_ms=400)
    add_check(service, 10, is_up=False)
    add_check(service, 5, response_time_ms=300)

    response = api_client.get(stats_url(service.slug))

    assert response.data["checks"] == 4
    assert response.data["uptime_percent"] == 75.0
    assert response.data["avg_response_time_ms"] == 300


def test_period_limits_checks(api_client, service):
    add_check(service, 60)
    add_check(service, 3 * 24 * 60)

    day = api_client.get(stats_url(service.slug), {"period": "24h"})
    week = api_client.get(stats_url(service.slug), {"period": "7d"})

    assert day.data["checks"] == 1
    assert week.data["checks"] == 2


def test_checks_are_split_by_alerts(api_client, service):
    Alert.objects.create(alert_level="red", started_at=ago(120), finished_at=ago(60))
    add_check(service, 90, is_up=False)
    add_check(service, 80, response_time_ms=900)
    add_check(service, 30, response_time_ms=200)
    add_check(service, 20, response_time_ms=300)

    alerts = api_client.get(stats_url(service.slug)).data["alerts"]

    assert alerts["during"] == {
        "checks": 2,
        "uptime_percent": 50.0,
        "avg_response_time_ms": 900,
    }
    assert alerts["without"] == {
        "checks": 2,
        "uptime_percent": 100.0,
        "avg_response_time_ms": 250,
    }
    assert alerts["by_level"]["red"]["checks"] == 2
    assert alerts["by_level"]["yellow"]["checks"] == 0


def test_active_alert_lasts_until_now(api_client, service):
    Alert.objects.create(alert_level="yellow", started_at=ago(30), finished_at=None)
    add_check(service, 60)
    add_check(service, 10)

    alerts = api_client.get(stats_url(service.slug)).data["alerts"]

    assert alerts["during"]["checks"] == 1
    assert alerts["by_level"]["yellow"]["checks"] == 1
    assert alerts["without"]["checks"] == 1


def test_outages_can_be_filtered_by_group(api_client, service):
    PowerOutage.objects.create(group="3.1", started_at=ago(120), finished_at=ago(60))
    PowerOutage.objects.create(group="5.2", started_at=ago(50), finished_at=ago(10))
    add_check(service, 90)
    add_check(service, 30)
    add_check(service, 5)

    any_group = api_client.get(stats_url(service.slug)).data["outages"]
    group_31 = api_client.get(stats_url(service.slug), {"group": "3.1"}).data["outages"]

    assert any_group["group"] is None
    assert any_group["during"]["checks"] == 2
    assert group_31["group"] == "3.1"
    assert group_31["during"]["checks"] == 1
    assert group_31["without"]["checks"] == 2


def test_checks_are_grouped_by_local_hour(api_client, service):
    check = add_check(service, 10)
    hour = timezone.localtime(check.checked_at).hour

    by_hour = api_client.get(stats_url(service.slug)).data["by_hour"]

    assert [item["hour"] for item in by_hour] == list(range(24))
    assert by_hour[hour]["checks"] == 1
    assert sum(item["checks"] for item in by_hour) == 1


def test_service_has_uptime_for_three_periods(api_client, service):
    add_check(service, 60)
    add_check(service, 3 * 24 * 60, is_up=False)
    add_check(service, 10 * 24 * 60, is_up=False)

    response = api_client.get(reverse("service-detail", args=[service.slug]))

    assert response.data["uptime"] == {"24h": 100.0, "7d": 50.0, "30d": 33.33}
