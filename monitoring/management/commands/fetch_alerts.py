from datetime import datetime
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from monitoring.models import Alert

API_URL = "https://api.alerts.in.ua/v1/alerts/active.json"
KYIV_CITY_UID = "31"
TIMEOUT_SECONDS = 10
KNOWN_LEVELS = {"yellow", "red"}


class Command(BaseCommand):
    help = "Завантажує активні тривоги з alerts.in.ua і оновлює тривоги Києва в Alert."

    def handle(self, *args, **options):
        if not settings.ALERTS_IN_UA_TOKEN:
            raise CommandError("Не задано ALERTS_IN_UA_TOKEN у файлі .env.")

        active_alerts = self.load_kyiv_alerts()
        active_ids = {str(alert["id"]) for alert in active_alerts}

        created, level_changed = self.save_active_alerts(active_alerts)
        finished = self.finish_ended_alerts(active_ids)

        if active_alerts:
            levels = ", ".join(
                sorted({self.level_of(alert) for alert in active_alerts})
            )
            self.stdout.write(self.style.WARNING(f"У Києві зараз тривога ({levels})."))
        else:
            self.stdout.write(self.style.SUCCESS("У Києві зараз тривоги немає."))
        self.stdout.write(
            f"Нових тривог: {created}, змінився рівень: {level_changed}, "
            f"завершених: {finished}."
        )

    def load_kyiv_alerts(self):
        headers = {"Authorization": f"Bearer {settings.ALERTS_IN_UA_TOKEN}"}
        try:
            response = requests.get(API_URL, headers=headers, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as error:
            raise CommandError(f"Не вдалося звернутися до API тривог: {error}")

        if response.status_code == 401:
            raise CommandError("API тривог не прийняло токен (401). Перевірте .env.")
        if response.status_code == 429:
            raise CommandError(
                "Забагато запитів до API тривог (429). Спробуйте пізніше."
            )
        if not response.ok:
            raise CommandError(f"API тривог повернуло помилку {response.status_code}.")

        alerts = response.json().get("alerts", [])
        return [alert for alert in alerts if alert["location_uid"] == KYIV_CITY_UID]

    def level_of(self, alert):
        level = alert.get("alert_level")
        return level if level in KNOWN_LEVELS else "red"

    def save_active_alerts(self, active_alerts):
        created_count = 0
        level_changed_count = 0
        for alert in active_alerts:
            level = self.level_of(alert)
            saved, created = Alert.objects.get_or_create(
                external_id=str(alert["id"]),
                defaults={
                    "alert_type": alert.get("alert_type", "air_raid"),
                    "alert_level": level,
                    "started_at": datetime.fromisoformat(alert["started_at"]),
                },
            )
            if created:
                created_count += 1
            elif saved.alert_level != level:
                saved.alert_level = level
                saved.save(update_fields=["alert_level"])
                level_changed_count += 1
        return created_count, level_changed_count

    def finish_ended_alerts(self, active_ids):
        ended = Alert.objects.filter(
            finished_at__isnull=True,
            external_id__isnull=False,
        ).exclude(external_id__in=active_ids)
        return ended.update(finished_at=timezone.now())
