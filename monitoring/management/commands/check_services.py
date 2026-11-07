import requests
from django.core.management.base import BaseCommand

from monitoring.models import Check, Service

TIMEOUT_SECONDS = 10
HEADERS = {"User-Agent": "DetectorAirRaid/0.1 (student project, uptime monitoring)"}


class Command(BaseCommand):
    help = "Перевіряє доступність усіх активних сервісів і записує результати в Check."

    def handle(self, *args, **options):
        services = Service.objects.filter(is_active=True)

        if not services.exists():
            self.stdout.write(
                self.style.WARNING("Немає активних сервісів для перевірки.")
            )
            return

        for service in services:
            check = self.check_service(service)

            if check.is_up:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{service.name}: працює ({check.status_code}, "
                        f"{check.response_time_ms} мс)"
                    )
                )
            else:
                details = check.status_code or "немає відповіді"
                self.stdout.write(
                    self.style.ERROR(f"{service.name}: не працює ({details})")
                )

    def check_service(self, service):
        try:
            response = requests.get(
                service.url, headers=HEADERS, timeout=TIMEOUT_SECONDS
            )
        except requests.RequestException as error:
            self.stdout.write(
                self.style.WARNING(f"  {service.url}: {type(error).__name__}: {error}")
            )
            return Check.objects.create(
                service=service,
                is_up=False,
                status_code=None,
                response_time_ms=None,
            )

        return Check.objects.create(
            service=service,
            is_up=response.status_code < 500,
            status_code=response.status_code,
            response_time_ms=int(response.elapsed.total_seconds() * 1000),
        )
