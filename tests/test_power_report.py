from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from monitoring.models import PowerReport

LIST_URL = reverse("power-report-list")


def detail_url(report_id):
    return reverse("power-report-detail", args=[report_id])




def test_guest_cannot_list_reports(api_client):
    response = api_client.get(LIST_URL)

    assert response.status_code == 401
    assert "Потрібно увійти" in response.data["error"]["message"]


def test_guest_cannot_create_report(api_client):
    response = api_client.post(LIST_URL, {"group": "2.1"}, format="json")

    assert response.status_code == 401
    assert PowerReport.objects.count() == 0


def test_guest_cannot_delete_report(api_client, report):
    response = api_client.delete(detail_url(report.id))

    assert response.status_code == 401
    assert PowerReport.objects.filter(id=report.id).exists()




def test_user_creates_report(user_client, user):
    payload = {"group": "3.1", "comment": "Немає світла з 18:00"}

    response = user_client.post(LIST_URL, payload, format="json")

    assert response.status_code == 201
    assert response.data["user"] == user.username
    assert response.data["group"] == "3.1"
    assert response.data["comment"] == "Немає світла з 18:00"
    assert PowerReport.objects.filter(user=user, group="3.1").count() == 1


def test_comment_is_optional(user_client):
    response = user_client.post(LIST_URL, {"group": "1.2"}, format="json")

    assert response.status_code == 201
    assert response.data["comment"] == ""


def test_author_is_taken_from_token_not_from_body(user_client, user, other_user):
    payload = {"group": "2.1", "user": other_user.username}

    response = user_client.post(LIST_URL, payload, format="json")

    assert response.status_code == 201
    assert PowerReport.objects.get().user == user


@pytest.mark.parametrize(
    "payload, field",
    [
        ({"group": "9.9"}, "group"),
        ({"group": ""}, "group"),
        ({}, "group"),
        ({"group": "2.1", "comment": "x" * 256}, "comment"),
    ],
    ids=["unknown-group", "empty-group", "no-group", "comment-too-long"],
)
def test_invalid_report_returns_400(user_client, payload, field):
    response = user_client.post(LIST_URL, payload, format="json")

    assert response.status_code == 400
    assert response.data["error"]["message"] == "Перевірте введені дані."
    assert field in response.data["error"]["details"]
    assert PowerReport.objects.count() == 0




def test_user_sees_only_own_reports(user_client, report, other_user):
    PowerReport.objects.create(user=other_user, group="5.2")

    response = user_client.get(LIST_URL)

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert [item["id"] for item in response.data["results"]] == [report.id]


def test_reports_are_sorted_newest_first(user_client, user):
    older = PowerReport.objects.create(user=user, group="1.1")
    newer = PowerReport.objects.create(user=user, group="1.2")
    PowerReport.objects.filter(id=older.id).update(
        created_at=timezone.now() - timedelta(hours=1)
    )

    response = user_client.get(LIST_URL)

    ids = [item["id"] for item in response.data["results"]]
    assert ids == [newer.id, older.id]


def test_staff_sees_reports_of_all_users(staff_client, report, other_user):
    other_report = PowerReport.objects.create(user=other_user, group="5.2")

    response = staff_client.get(LIST_URL)

    assert response.status_code == 200
    ids = {item["id"] for item in response.data["results"]}
    assert ids == {report.id, other_report.id}


def test_filter_reports_by_group(staff_client, report, other_user):
    PowerReport.objects.create(user=other_user, group="5.2")

    response = staff_client.get(LIST_URL, {"group": "2.1"})

    assert response.data["count"] == 1
    assert response.data["results"][0]["group"] == "2.1"




def test_user_gets_own_report(user_client, report):
    response = user_client.get(detail_url(report.id))

    assert response.status_code == 200
    assert response.data["id"] == report.id
    assert response.data["comment"] == report.comment


def test_user_cannot_see_someone_elses_report(other_client, report):
    response = other_client.get(detail_url(report.id))

    assert response.status_code == 404
    assert response.data["error"]["message"] == "Заявку не знайдено."


def test_nonexistent_report_returns_404(user_client):
    response = user_client.get(detail_url(99999))

    assert response.status_code == 404




def test_user_deletes_own_report(user_client, report):
    response = user_client.delete(detail_url(report.id))

    assert response.status_code == 204
    assert not PowerReport.objects.filter(id=report.id).exists()


def test_user_cannot_delete_someone_elses_report(other_client, report):
    response = other_client.delete(detail_url(report.id))

    assert response.status_code == 404
    assert PowerReport.objects.filter(id=report.id).exists()


def test_staff_deletes_any_report(staff_client, report):
    response = staff_client.delete(detail_url(report.id))

    assert response.status_code == 204
    assert not PowerReport.objects.filter(id=report.id).exists()


def test_deleting_nonexistent_report_returns_404(user_client):
    response = user_client.delete(detail_url(99999))

    assert response.status_code == 404




@pytest.mark.parametrize("method", ["put", "patch"])
def test_report_cannot_be_edited(user_client, report, method):
    send = getattr(user_client, method)

    response = send(detail_url(report.id), {"group": "6.2"}, format="json")

    assert response.status_code == 405
    report.refresh_from_db()
    assert report.group == "2.1"
