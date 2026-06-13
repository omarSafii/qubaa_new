from __future__ import annotations

from collections import OrderedDict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from halaqas.models import Attendance, HalaqaMembership
from students.models import MemorizationRecord, Student


RELATED_MODELS = OrderedDict(
    [
        ("memorization_records", MemorizationRecord),
        ("attendances", Attendance),
        ("point_transactions", None),
        ("plans", None),
        ("homeworks", None),
    ]
)


class Command(BaseCommand):
    help = "Safely merge one duplicate Student record into another without deleting history records."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--keep-id", required=True, type=int)
        parser.add_argument("--remove-id", required=True, type=int)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--commit", action="store_true")

    def handle(self, *args, **options):
        dry_run = not options["commit"]
        keep = self._get_student(options["keep_id"], options["name"], "keep")
        remove = self._get_student(options["remove_id"], options["name"], "remove")
        if keep.pk == remove.pk:
            raise CommandError("--keep-id and --remove-id must be different students.")

        plan = self._build_plan(keep, remove)
        self._print_plan(keep, remove, plan, dry_run)

        if plan["blockers"]:
            raise CommandError("Merge blocked. Resolve blockers before committing.")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run only. No database changes were written."))
            return

        remove_id = remove.pk
        with transaction.atomic():
            self._merge_memberships(keep, remove)
            self._move_simple_relations(keep, remove)
            self._fill_missing_profile_fields(keep, remove)
            remove.delete()
            self._sync_keep_snapshot(keep)

        self.stdout.write(self.style.SUCCESS(f"Merged student {remove_id} into {keep.pk}. Duplicate Student row deleted after relations were moved."))

    def _get_student(self, student_id: int, expected_name: str, label: str) -> Student:
        try:
            student = Student.objects.get(pk=student_id)
        except Student.DoesNotExist as exc:
            raise CommandError(f"{label} student not found: {student_id}") from exc
        if student.name != expected_name:
            raise CommandError(f"{label} student id={student_id} has name {student.name!r}, expected {expected_name!r}.")
        return student

    def _build_plan(self, keep: Student, remove: Student):
        plan = {
            "counts": self._related_counts(keep, remove),
            "membership_moves": [],
            "membership_merges": [],
            "simple_moves": {},
            "blockers": [],
        }

        for membership in HalaqaMembership.objects.filter(student=remove).select_related("halaqa").order_by("id"):
            existing = HalaqaMembership.objects.filter(student=keep, halaqa=membership.halaqa).first()
            if existing:
                plan["membership_merges"].append((membership, existing))
            else:
                plan["membership_moves"].append(membership)

        for attendance in Attendance.objects.filter(student=remove).select_related("session__halaqa").order_by("id"):
            if Attendance.objects.filter(student=keep, session=attendance.session).exists():
                plan["blockers"].append(
                    f"Attendance conflict: remove attendance id={attendance.pk} has same session={attendance.session_id} as kept student."
                )

        for relation_name in ["memorization_records", "attendances", "point_transactions", "plans", "homeworks"]:
            manager = getattr(remove, relation_name)
            plan["simple_moves"][relation_name] = manager.count()

        return plan

    def _related_counts(self, keep: Student, remove: Student):
        names = ["halaqa_memberships", "memorization_records", "attendances", "point_transactions", "plans", "homeworks"]
        return {
            name: {
                "keep": getattr(keep, name).count(),
                "remove": getattr(remove, name).count(),
            }
            for name in names
        }

    def _print_plan(self, keep: Student, remove: Student, plan, dry_run: bool):
        self.stdout.write(self.style.NOTICE("Student merge plan"))
        self.stdout.write(f"Mode: {'dry-run' if dry_run else 'commit'}")
        self.stdout.write(f"Keep: id={keep.pk}, name={keep.name}, current_halaqa={self._current_halaqa_name(keep)}")
        self.stdout.write(f"Remove: id={remove.pk}, name={remove.name}, current_halaqa={self._current_halaqa_name(remove)}")
        self.stdout.write("")
        self.stdout.write("Related history counts")
        for name, counts in plan["counts"].items():
            self.stdout.write(f"- {name}: keep={counts['keep']}, remove={counts['remove']}")
        self.stdout.write("")
        self.stdout.write("Membership actions")
        for membership in plan["membership_moves"]:
            self.stdout.write(f"- move membership id={membership.pk} halaqa={membership.halaqa.name} active={membership.is_active}")
        for source, target in plan["membership_merges"]:
            self.stdout.write(
                f"- merge membership id={source.pk} into id={target.pk} halaqa={source.halaqa.name} active={source.is_active}"
            )
        self.stdout.write("")
        self.stdout.write("Record moves")
        for name, count in plan["simple_moves"].items():
            self.stdout.write(f"- {name}: {count}")
        if plan["blockers"]:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR("Blockers"))
            for blocker in plan["blockers"]:
                self.stdout.write(f"- {blocker}")

    def _current_halaqa_name(self, student: Student) -> str:
        membership = (
            HalaqaMembership.objects.filter(student=student, is_active=True)
            .select_related("halaqa")
            .order_by("-join_date", "-id")
            .first()
        )
        current = membership.halaqa if membership else student.halaqa
        return current.name if current else "none"

    def _merge_memberships(self, keep: Student, remove: Student):
        today = timezone.localdate()
        for source in HalaqaMembership.objects.filter(student=remove).select_related("halaqa").order_by("id"):
            target = HalaqaMembership.objects.filter(student=keep, halaqa=source.halaqa).first()
            if target:
                updates = {}
                if source.join_date and (not target.join_date or source.join_date < target.join_date):
                    updates["join_date"] = source.join_date
                if not target.is_active and source.is_active:
                    updates["end_date"] = target.end_date or today
                elif source.end_date and (not target.end_date or source.end_date > target.end_date):
                    updates["end_date"] = source.end_date
                if updates:
                    HalaqaMembership.objects.filter(pk=target.pk).update(**updates)
                source.delete()
                continue

            if source.is_active:
                active_keep_memberships = HalaqaMembership.objects.filter(student=keep, is_active=True)
                active_keep_memberships.filter(end_date__isnull=True).update(end_date=today)
                active_keep_memberships.update(is_active=False)
            HalaqaMembership.objects.filter(pk=source.pk).update(student=keep)

    def _move_simple_relations(self, keep: Student, remove: Student):
        remove.memorization_records.update(student=keep)
        remove.attendances.update(student=keep)
        remove.point_transactions.update(student=keep)
        remove.plans.update(student=keep)
        remove.homeworks.update(student=keep)

    def _fill_missing_profile_fields(self, keep: Student, remove: Student):
        updates = {}
        for field_name in ["parent", "parent_phone", "address", "grade", "category", "halaqa", "enrollment_date", "created_by"]:
            keep_value = getattr(keep, field_name)
            remove_value = getattr(remove, field_name)
            if not keep_value and remove_value:
                setattr(keep, field_name, remove_value)
                updates[field_name] = remove_value
        if updates:
            keep.save(update_fields=list(updates))

    def _sync_keep_snapshot(self, keep: Student):
        active_membership = (
            HalaqaMembership.objects.filter(student=keep, is_active=True)
            .select_related("halaqa__category")
            .order_by("-join_date", "-id")
            .first()
        )
        if active_membership:
            Student.objects.filter(pk=keep.pk).update(
                halaqa=active_membership.halaqa,
                category=active_membership.halaqa.category or keep.category,
            )
