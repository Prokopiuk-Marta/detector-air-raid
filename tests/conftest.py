import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from monitoring.models import PowerReport, Service

User = get_user_model()

PASSWORD = "Svitlo2026!"


@pytest.fixture(autouse=True)
def enable_db_access(db):
    """Дає кожному тесту доступ до тестової бази даних."""


@pytest.fixture(autouse=True)
def fast_password_hasher(settings):
    """Швидкий хешер паролів лише для тестів: справжній навмисно повільний."""
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def api_client():
    """Клієнт без входу (гість)."""
    return APIClient()


@pytest.fixture
def user():
    return User.objects.create_user(
        username="marta", email="marta@example.com", password=PASSWORD
    )


@pytest.fixture
def other_user():
    return User.objects.create_user(
        username="sofia", email="sofia@example.com", password=PASSWORD
    )


@pytest.fixture
def staff_user():
    return User.objects.create_user(
        username="admin", email="admin@example.com", password=PASSWORD, is_staff=True
    )


def make_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def user_client(user):
    """Клієнт, який увійшов як звичайний користувач."""
    return make_client(user)


@pytest.fixture
def other_client(other_user):
    """Клієнт іншого звичайного користувача."""
    return make_client(other_user)


@pytest.fixture
def staff_client(staff_user):
    """Клієнт, який увійшов як адміністратор."""
    return make_client(staff_user)


@pytest.fixture
def service():
    return Service.objects.create(
        name="Дія", slug="diia", url="https://diia.gov.ua", description="Держпослуги"
    )


@pytest.fixture
def report(user):
    """Заявка, яку подав user."""
    return PowerReport.objects.create(user=user, group="2.1", comment="З 18:00")
