import logging
import time

import requests
from django.core.management.base import BaseCommand

from monitoring.models import Check, Service

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10
HEADERS = {"User-Agent": "DetectorAirRaid/0.1 (student project, uptime monitoring)"}


class Command(BaseCommand):
    help = "Перевіряє доступність усіх активних сервісів і записує результати в Check."

    def handle(self, *args, **options):
        services = Service.objects.filter(is_active=True)

        if not services.exists():
            logger.warning("Немає активних сервісів для перевірки")
            self.stdout.write(
                self.style.WARNING("Немає активних сервісів для перевірки.")
            )
            return

        started = time.monotonic()
        down = 0
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
                down += 1
                details = check.status_code or "немає відповіді"
                self.stdout.write(
                    self.style.ERROR(f"{service.name}: не працює ({details})")
                )

        logger.info(
            "Перевірено сервісів: %s, не працює: %s, за %.1f с",
            services.count(),
            down,
            time.monotonic() - started,
        )

    def check_service(self, service):
        try:
            response = requests.get(
                service.url, headers=HEADERS, timeout=TIMEOUT_SECONDS
            )
        except requests.RequestException as error:
            logger.warning("%s недоступний: %s", service.slug, type(error).__name__)
            self.stdout.write(
                self.style.WARNING(f"  {service.url}: {type(error).__name__}: {error}")
            )
            return Check.objects.create(
                service=service,
                is_up=False,
                status_code=None,
                response_time_ms=None,
            )

        if response.status_code >= 500:
            logger.warning(
                "%s повернув помилку сервера %s", service.slug, response.status_code
            )
        else:
            logger.debug(
                "%s працює: %s, %s",
                service.slug,
                response.status_code,
                response.elapsed,
            )

        return Check.objects.create(
            service=service,
            is_up=response.status_code < 500,
            status_code=response.status_code,
            response_time_ms=int(response.elapsed.total_seconds() * 1000),
        )
