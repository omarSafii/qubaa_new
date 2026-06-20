import secrets

from django.core.management.base import BaseCommand, CommandError

from halaqas.models import Halaqa


DEFAULT_BASE_URL = "https://omarsafi.pythonanywhere.com"
MIN_TOKEN_LENGTH = 40


class Command(BaseCommand):
    help = "Generate, show, or reset a private direct access link for one halaqa."

    def add_arguments(self, parser):
        parser.add_argument("--halaqa-id", type=int, required=True, help="Halaqa ID to generate the link for.")
        parser.add_argument("--reset", action="store_true", help="Invalidate the current token and create a new one.")
        parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL used when printing the full link.")

    def handle(self, *args, **options):
        try:
            halaqa = Halaqa.objects.get(pk=options["halaqa_id"])
        except Halaqa.DoesNotExist as exc:
            raise CommandError(f"Halaqa with id {options['halaqa_id']} does not exist.") from exc

        if options["reset"] or not halaqa.shareable_link or len(halaqa.shareable_link) < MIN_TOKEN_LENGTH:
            halaqa.shareable_link = secrets.token_urlsafe(32)
            halaqa.save(update_fields=["shareable_link"])
            action = "Reset halaqa share link" if options["reset"] else "Generated halaqa share link"
        else:
            action = "Current halaqa share link"

        base_url = options["base_url"].rstrip("/")
        self.stdout.write(self.style.SUCCESS(action))
        self.stdout.write(f"{base_url}/halaqas/halaqa/{halaqa.pk}/?key={halaqa.shareable_link}")
