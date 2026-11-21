"""Тести логування: потрібні події записуються, а паролі й токени — ніколи.

caplog — вбудована фікстура pytest, яка перехоплює все, що записано в лог під час тесту.
"""

import logging

import pytest
from django.urls import reverse

from tests.conftest import PASSWORD

SECRET_PASSWORD = "Svitlo2026!"


@pytest.fixture(autouse=True)
def capture_info_logs(caplog):
    caplog.set_level(logging.INFO)


def test_registration_is_logged_without_password(api_client, caplog):
    api_client.post(
        reverse("register"),
        {
            "username": "vira",
            "email": "vira@example.com",
            "password": SECRET_PASSWORD,
            "password_confirm": SECRET_PASSWORD,
        },
        format="json",
    )

    assert "Зареєстровано користувача vira" in caplog.text
    assert SECRET_PASSWORD not in caplog.text


def test_login_is_logged_without_password_and_tokens(api_client, user, caplog):
    response = api_client.post(
        reverse("token-obtain"),
        {"username": user.username, "password": PASSWORD},
        format="json",
    )

    assert f"Успішний вхід: {user.username}" in caplog.text
    assert PASSWORD not in caplog.text
    assert response.data["access"] not in caplog.text
    assert response.data["refresh"] not in caplog.text


def test_failed_login_is_logged_as_warning(api_client, user, caplog):
    api_client.post(
        reverse("token-obtain"),
        {"username": user.username, "password": "wrong-password"},
        format="json",
    )

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Неправильний логін або пароль" in r.getMessage() for r in warnings)
    assert "wrong-password" not in caplog.text


def test_forbidden_action_is_logged_with_user(user_client, user, caplog):
    user_client.delete(reverse("service-detail", args=["diia"]))

    assert "DELETE /api/v1/services/diia/ -> 403" in caplog.text
    assert user.username in caplog.text


def test_invalid_data_logs_only_field_names(user_client, caplog):
    user_client.post(
        reverse("power-report-list"),
        {"group": "9.9", "comment": "секретний коментар"},
        format="json",
    )

    assert "помилки в полях ['group']" in caplog.text
    assert "секретний коментар" not in caplog.text


def test_new_power_report_is_logged(user_client, user, caplog):
    user_client.post(reverse("power-report-list"), {"group": "3.1"}, format="json")

    assert "Нова заявка" in caplog.text
    assert "група 3.1" in caplog.text
    assert user.username in caplog.text
