import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from tests.conftest import PASSWORD

User = get_user_model()

REGISTER_URL = reverse("register")
TOKEN_URL = reverse("token-obtain")
REFRESH_URL = reverse("token-refresh")
ME_URL = reverse("me")

VALID_REGISTRATION = {
    "username": "vira",
    "email": "vira@example.com",
    "first_name": "Віра",
    "password": "Svitlo2026!",
    "password_confirm": "Svitlo2026!",
}


def get_tokens(client, username, password=PASSWORD):
    response = client.post(
        TOKEN_URL, {"username": username, "password": password}, format="json"
    )
    return response.data




def test_register_creates_user_with_hashed_password(api_client):
    response = api_client.post(REGISTER_URL, VALID_REGISTRATION, format="json")

    assert response.status_code == 201
    assert response.data["username"] == "vira"
    assert response.data["is_staff"] is False
    assert "password" not in response.data
    assert "password_confirm" not in response.data

    user = User.objects.get(username="vira")
    assert user.password != "Svitlo2026!"
    assert user.check_password("Svitlo2026!")


@pytest.mark.parametrize(
    "changes, field",
    [
        ({"username": ""}, "username"),
        ({"email": ""}, "email"),
        ({"email": "not-an-email"}, "email"),
        ({"password": "Short1!", "password_confirm": "Short1!"}, "password"),
        ({"password": "1234567890", "password_confirm": "1234567890"}, "password"),
        (
            {"password": "vira@example.com", "password_confirm": "vira@example.com"},
            "password",
        ),
        ({"password_confirm": "Svitlo2026?"}, "password_confirm"),
        ({"username": "x" * 151}, "username"),
    ],
    ids=[
        "empty-username",
        "empty-email",
        "invalid-email",
        "short-password",
        "numeric-password",
        "password-like-email",
        "passwords-do-not-match",
        "too-long-username",
    ],
)
def test_invalid_registration_returns_400(api_client, changes, field):
    payload = {**VALID_REGISTRATION, **changes}

    response = api_client.post(REGISTER_URL, payload, format="json")

    assert response.status_code == 400
    assert field in response.data["error"]["details"]
    assert not User.objects.filter(email=VALID_REGISTRATION["email"]).exists()


def test_register_requires_all_mandatory_fields(api_client):
    response = api_client.post(REGISTER_URL, {}, format="json")

    assert response.status_code == 400
    details = response.data["error"]["details"]
    assert {"username", "email", "password", "password_confirm"} <= set(details)


def test_cannot_register_with_taken_email_in_other_case(api_client, user):
    payload = {**VALID_REGISTRATION, "email": user.email.upper()}

    response = api_client.post(REGISTER_URL, payload, format="json")

    assert response.status_code == 400
    assert response.data["error"]["details"]["email"] == [
        "Користувач з таким email уже існує."
    ]


def test_cannot_register_with_taken_username(api_client, user):
    payload = {**VALID_REGISTRATION, "username": user.username}

    response = api_client.post(REGISTER_URL, payload, format="json")

    assert response.status_code == 400
    assert "username" in response.data["error"]["details"]




def test_login_returns_access_and_refresh(api_client, user):
    response = api_client.post(
        TOKEN_URL, {"username": user.username, "password": PASSWORD}, format="json"
    )

    assert response.status_code == 200
    assert set(response.data) == {"access", "refresh"}


def test_login_with_wrong_password_returns_401(api_client, user):
    response = api_client.post(
        TOKEN_URL, {"username": user.username, "password": "wrong"}, format="json"
    )

    assert response.status_code == 401
    assert response.data["error"]["message"] == "Неправильний логін або пароль."


def test_refresh_returns_new_access_token(api_client, user):
    tokens = get_tokens(api_client, user.username)

    response = api_client.post(
        REFRESH_URL, {"refresh": tokens["refresh"]}, format="json"
    )

    assert response.status_code == 200
    assert "access" in response.data


def test_refresh_with_invalid_token_returns_401(api_client):
    response = api_client.post(REFRESH_URL, {"refresh": "not-a-token"}, format="json")

    assert response.status_code == 401
    assert "Токен недійсний" in response.data["error"]["message"]




def test_me_with_access_token(api_client, user):
    tokens = get_tokens(api_client, user.username)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    response = api_client.get(ME_URL)

    assert response.status_code == 200
    assert response.data["username"] == user.username
    assert response.data["is_staff"] is False


def test_me_without_token_returns_401(api_client):
    response = api_client.get(ME_URL)

    assert response.status_code == 401
    assert "Authorization: Bearer" in response.data["error"]["message"]


def test_invalid_token_returns_401_even_on_public_endpoint(api_client):
    api_client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token")

    response = api_client.get(reverse("service-list"))

    assert response.status_code == 401
    assert "Токен недійсний" in response.data["error"]["message"]


def test_full_flow_register_login_and_create_report(api_client):
    api_client.post(REGISTER_URL, VALID_REGISTRATION, format="json")
    tokens = get_tokens(api_client, "vira", "Svitlo2026!")
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    response = api_client.post(
        reverse("power-report-list"), {"group": "4.1"}, format="json"
    )

    assert response.status_code == 201
    assert response.data["user"] == "vira"
