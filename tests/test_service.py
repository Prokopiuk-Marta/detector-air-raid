from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from monitoring.models import Check, Incident, Service

LIST_URL = reverse("service-list")

NEW_SERVICE = {
    "name": "Укрзалізниця",
    "slug": "uz",
    "url": "https://uz.gov.ua",
    "description": "Квитки на потяги",
}


def detail_url(slug):
    return reverse("service-detail", args=[slug])


def test_guest_sees_service_list(api_client, service):
    response = api_client.get(LIST_URL)

    assert response.status_code == 200
    assert [item["slug"] for item in response.data] == ["diia"]


def test_service_without_checks_has_unknown_status(api_client, service):
    response = api_client.get(detail_url(service.slug))

    assert response.status_code == 200
    assert response.data["status"] == "unknown"
    assert response.data["uptime_7d"] is None


def test_service_status_and_uptime_are_calculated_from_checks(api_client, service):
    now = timezone.now()
    for minutes_ago, is_up in [(20, True), (15, True), (10, False), (5, True)]:
        Check.objects.create(
            service=service,
            checked_at=now - timedelta(minutes=minutes_ago),
            is_up=is_up,
            status_code=200 if is_up else 503,
            response_time_ms=300,
        )
    Check.objects.create(
        service=service, checked_at=now - timedelta(days=8), is_up=False
    )

    response = api_client.get(detail_url(service.slug))

    assert response.data["status"] == "up"
    assert response.data["response_time_ms"] == 300
    assert response.data["uptime_7d"] == 75.0


def test_nonexistent_service_returns_404(api_client):
    response = api_client.get(detail_url("netflix"))

    assert response.status_code == 404
    assert response.data["error"]["message"] == "Сервіс 'netflix' не знайдено."


def test_guest_cannot_create_service(api_client):
    response = api_client.post(LIST_URL, NEW_SERVICE, format="json")

    assert response.status_code == 401
    assert not Service.objects.filter(slug="uz").exists()


def test_guest_cannot_update_service(api_client, service):
    response = api_client.patch(detail_url(service.slug), {"name": "X"}, format="json")

    assert response.status_code == 401


def test_guest_cannot_delete_service(api_client, service):
    response = api_client.delete(detail_url(service.slug))

    assert response.status_code == 401
    assert Service.objects.filter(slug=service.slug).exists()


def test_user_cannot_create_service(user_client):
    response = user_client.post(LIST_URL, NEW_SERVICE, format="json")

    assert response.status_code == 403
    assert "лише адміністратор" in response.data["error"]["message"]
    assert not Service.objects.filter(slug="uz").exists()


def test_user_cannot_update_service(user_client, service):
    response = user_client.patch(detail_url(service.slug), {"name": "X"}, format="json")

    assert response.status_code == 403
    service.refresh_from_db()
    assert service.name == "Дія"


def test_user_cannot_delete_service(user_client, service):
    response = user_client.delete(detail_url(service.slug))

    assert response.status_code == 403
    assert Service.objects.filter(slug=service.slug).exists()


def test_staff_creates_service(staff_client):
    response = staff_client.post(LIST_URL, NEW_SERVICE, format="json")

    assert response.status_code == 201
    assert response.data["slug"] == "uz"
    assert response.data["is_active"] is True
    assert Service.objects.filter(slug="uz", name="Укрзалізниця").exists()


@pytest.mark.parametrize(
    "changes, field",
    [
        ({"name": ""}, "name"),
        ({"url": "not-a-url"}, "url"),
        ({"slug": "з пробілами"}, "slug"),
        ({"slug": "diia"}, "slug"),
    ],
    ids=["empty-name", "invalid-url", "invalid-slug", "duplicate-slug"],
)
def test_invalid_service_returns_400(staff_client, service, changes, field):
    payload = {**NEW_SERVICE, **changes}

    response = staff_client.post(LIST_URL, payload, format="json")

    assert response.status_code == 400
    assert field in response.data["error"]["details"]
    assert Service.objects.count() == 1


def test_staff_updates_only_given_fields(staff_client, service):
    response = staff_client.patch(
        detail_url(service.slug), {"is_active": False}, format="json"
    )

    assert response.status_code == 200
    service.refresh_from_db()
    assert service.is_active is False
    assert service.name == "Дія"


def test_staff_update_with_invalid_url_returns_400(staff_client, service):
    response = staff_client.patch(
        detail_url(service.slug), {"url": "not-a-url"}, format="json"
    )

    assert response.status_code == 400
    assert "url" in response.data["error"]["details"]


def test_staff_deletes_service_without_history(staff_client, service):
    response = staff_client.delete(detail_url(service.slug))

    assert response.status_code == 204
    assert not Service.objects.filter(slug=service.slug).exists()


def test_cannot_delete_service_with_checks(staff_client, service):
    Check.objects.create(service=service, is_up=True, status_code=200)

    response = staff_client.delete(detail_url(service.slug))

    assert response.status_code == 409
    assert "деактивуйте сервіс" in response.data["error"]["message"]
    assert Service.objects.filter(slug=service.slug).exists()


def test_cannot_delete_service_mentioned_in_incident(staff_client, service):
    incident = Incident.objects.create(title="Збій", started_at=timezone.now())
    incident.services.add(service)

    response = staff_client.delete(detail_url(service.slug))

    assert response.status_code == 409
    assert "інцидентах" in response.data["error"]["message"]
    assert Service.objects.filter(slug=service.slug).exists()


def test_deleting_nonexistent_service_returns_404(staff_client):
    response = staff_client.delete(detail_url("netflix"))

    assert response.status_code == 404
