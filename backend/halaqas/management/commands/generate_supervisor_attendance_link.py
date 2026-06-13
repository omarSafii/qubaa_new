import secrets

from django.core.management.base import BaseCommand

from halaqas.models import SupervisorAttendanceShare


DEFAULT_BASE_URL = "https://omarsafi.pythonanywhere.com"


class Command(BaseCommand):
    help = "Generate, show, or reset the public supervisor attendance share link."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Invalidate the current token and create a new one.")
        parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL used when printing the full link.")

    def handle(self, *args, **options):
        if options["reset"]:
            SupervisorAttendanceShare.objects.filter(is_active=True).update(is_active=False)
            share = SupervisorAttendanceShare.objects.create(token=secrets.token_urlsafe(32), is_active=True)
            action = "Reset supervisor attendance link"
        else:
            share = SupervisorAttendanceShare.objects.filter(is_active=True).order_by("-updated_at", "-id").first()
            if share is None:
                share = SupervisorAttendanceShare.objects.create(token=secrets.token_urlsafe(32), is_active=True)
                action = "Generated supervisor attendance link"
            else:
                action = "Current supervisor attendance link"

        base_url = options["base_url"].rstrip("/")
        self.stdout.write(self.style.SUCCESS(action))
        self.stdout.write(f"{base_url}/halaqas/supervisor/share/{share.token}/")
