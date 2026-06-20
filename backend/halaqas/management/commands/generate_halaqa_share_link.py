import csv
import secrets
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from halaqas.models import Halaqa


DEFAULT_BASE_URL = "https://omarsafi.pythonanywhere.com"


class Command(BaseCommand):
    help = "Generate, show, or reset private direct access links for halaqas."

    def add_arguments(self, parser):
        parser.add_argument("--halaqa-id", type=int, help="Halaqa ID to generate/show the link for.")
        parser.add_argument("--all", action="store_true", help="Generate/show links for all active halaqas.")
        parser.add_argument("--reset", action="store_true", help="Invalidate the current token and create a new one.")
        parser.add_argument("--output", help="Optional CSV output path. Intended for use with --all.")
        parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL used when printing the full link.")

    def handle(self, *args, **options):
        if bool(options["halaqa_id"]) == bool(options["all"]):
            raise CommandError("Provide exactly one of --halaqa-id or --all.")
        if options["output"] and not options["all"]:
            raise CommandError("--output is only supported with --all.")

        base_url = options["base_url"].rstrip("/")

        if options["all"]:
            self._handle_all(base_url, options["reset"], options["output"])
            return

        try:
            halaqa = Halaqa.objects.get(pk=options["halaqa_id"])
        except Halaqa.DoesNotExist as exc:
            raise CommandError(f"Halaqa with id {options['halaqa_id']} does not exist.") from exc

        action = self._ensure_token(halaqa, reset=options["reset"])

        self.stdout.write(self.style.SUCCESS(action))
        self.stdout.write(self._direct_link(base_url, halaqa))

    def _handle_all(self, base_url, reset, output):
        if reset:
            warning = "WARNING: --all --reset will invalidate every existing halaqa direct-access link."
            self.stdout.write(self.style.WARNING(warning))

        rows = []
        halaqas = (
            Halaqa.objects.filter(is_active=True)
            .prefetch_related("teachers")
            .order_by("id")
        )

        for halaqa in halaqas:
            action = self._ensure_token(halaqa, reset=reset)
            teacher_names = self._teacher_names(halaqa)
            direct_link = self._direct_link(base_url, halaqa)
            rows.append(
                {
                    "halaqa_id": halaqa.id,
                    "halaqa_name": halaqa.name,
                    "teachers": teacher_names,
                    "direct_link": direct_link,
                    "notes": action,
                }
            )
            self.stdout.write(f"{halaqa.id} | {halaqa.name} | {teacher_names or 'No assigned teachers'} | {direct_link}")

        if output:
            self._write_csv(output, rows)
            self.stdout.write(self.style.SUCCESS(f"CSV written: {output}"))

        if reset:
            self.stdout.write(self.style.WARNING("WARNING COMPLETE: all old halaqa direct-access links were invalidated."))

        self.stdout.write(self.style.SUCCESS(f"Processed {len(rows)} active halaqa(s)."))

    def _ensure_token(self, halaqa, reset=False):
        if reset or not halaqa.shareable_link:
            halaqa.shareable_link = secrets.token_urlsafe(32)
            halaqa.save(update_fields=["shareable_link"])
            return "Reset halaqa share link" if reset else "Generated halaqa share link"
        return "Current halaqa share link"

    def _direct_link(self, base_url, halaqa):
        return f"{base_url}/halaqas/halaqa/{halaqa.pk}/?key={halaqa.shareable_link}"

    def _teacher_names(self, halaqa):
        return ", ".join(teacher.full_name for teacher in halaqa.teachers.all())

    def _write_csv(self, output, rows):
        output_path = Path(output)
        if output_path.parent and str(output_path.parent) != ".":
            output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=["halaqa_id", "halaqa_name", "teachers", "direct_link", "notes"],
            )
            writer.writeheader()
            writer.writerows(rows)
