from __future__ import annotations

import csv
import re
import secrets
import unicodedata
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Profile
from halaqas.access import assigned_halaqas_for_teacher
from halaqas.models import Teacher


LOGIN_LINK = "https://omarsafi.pythonanywhere.com/accounts/login/"
PASSWORD_UNAVAILABLE_MESSAGE = (
    "لا يمكن عرض كلمة المرور الحالية لأن النظام يحفظها مشفرة. "
    "استخدم --reset-passwords لتوليد كلمات مرور أولية جديدة."
)
INITIAL_PASSWORD_WARNING = (
    "هذه كلمات مرور أولية. أرسل كل كلمة مرور بشكل خاص للأستاذ صاحبها."
)


class Command(BaseCommand):
    help = "Generate a teacher login access report and optionally reset initial passwords."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Generate and set new initial passwords for teacher users.",
        )
        parser.add_argument(
            "--create-missing-users",
            action="store_true",
            help="Repair missing Profile records and teacher roles where possible.",
        )
        parser.add_argument(
            "--output",
            help="Optional CSV output path, for example backend/import_data/teacher_access_report.csv.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reset_passwords = options["reset_passwords"]
        create_missing_users = options["create_missing_users"]
        output = options.get("output")

        if reset_passwords:
            self.stdout.write(self.style.WARNING(INITIAL_PASSWORD_WARNING))

        rows = []
        teachers = Teacher.objects.select_related("user").order_by("full_name", "user__username")
        for index, teacher in enumerate(teachers, start=1):
            rows.append(
                self._build_teacher_row(
                    teacher=teacher,
                    index=index,
                    reset_passwords=reset_passwords,
                    create_missing_users=create_missing_users,
                )
            )

        if not rows:
            self.stdout.write(self.style.WARNING("لا يوجد أساتذة في قاعدة البيانات."))
            return

        for row in rows:
            self.stdout.write(self._format_whatsapp_block(row))
            self.stdout.write("")

        if output:
            self._write_csv(Path(output), rows)
            self.stdout.write(self.style.SUCCESS(f"تم إنشاء ملف CSV: {output}"))

    def _build_teacher_row(self, *, teacher, index, reset_passwords, create_missing_users):
        notes = []
        user = getattr(teacher, "user", None)
        password = ""

        if user is None:
            notes.append("لا يوجد حساب مستخدم مرتبط بهذا الأستاذ. هذا غير متوقع في البنية الحالية.")
            if create_missing_users:
                notes.append("تعذر إنشاء حساب جديد لأن Teacher مرتبط إلزامياً بـ User في النموذج الحالي.")
            username = ""
        else:
            username = user.username or self._generate_username(teacher.full_name, index)
            if username != user.username:
                user.username = self._unique_username(username)
                user.save(update_fields=["username"])
                username = user.username
                notes.append("تم إصلاح اسم المستخدم.")

            profile = getattr(user, "profile", None)
            if profile is None:
                if create_missing_users:
                    profile = Profile.objects.create(user=user, role="teacher")
                    notes.append("تم إنشاء ملف Profile بدور teacher.")
                else:
                    notes.append("لا يوجد Profile مرتبط بالمستخدم. استخدم --create-missing-users لإصلاحه.")
            elif profile.role != "teacher":
                if create_missing_users:
                    profile.role = "teacher"
                    profile.save(update_fields=["role"])
                    notes.append("تم ضبط الدور إلى teacher.")
                else:
                    notes.append(f"الدور الحالي ليس teacher: {profile.role}")

            if reset_passwords:
                password = self._generate_password()
                user.set_password(password)
                user.save(update_fields=["password"])

        halaqa_names = [halaqa.name for halaqa in assigned_halaqas_for_teacher(teacher)]
        if not halaqa_names:
            notes.append("لا توجد حلقات مسندة.")

        return {
            "teacher_name": teacher.full_name,
            "halaqas": "، ".join(halaqa_names) if halaqa_names else "لا توجد حلقات مسندة",
            "username": username,
            "password": password if reset_passwords else PASSWORD_UNAVAILABLE_MESSAGE,
            "login_link": LOGIN_LINK,
            "notes": " | ".join(notes),
        }

    def _format_whatsapp_block(self, row):
        lines = [
            "السلام عليكم ورحمة الله وبركاته",
            f"الأستاذ: {row['teacher_name']}",
            f"الحلقة: {row['halaqas']}",
            f"رابط الدخول: {row['login_link']}",
            f"اسم المستخدم: {row['username']}",
            f"كلمة المرور: {row['password']}",
            "تنبيه: الرجاء عدم مشاركة بيانات الدخول مع أحد.",
        ]
        if row["notes"]:
            lines.append(f"ملاحظات: {row['notes']}")
        return "\n".join(lines)

    def _write_csv(self, output_path, rows):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=["teacher_name", "halaqas", "username", "password", "login_link", "notes"],
            )
            writer.writeheader()
            writer.writerows(rows)

    def _generate_password(self):
        return f"Qubaa-{secrets.randbelow(90000) + 10000}"

    def _generate_username(self, full_name, index):
        normalized = unicodedata.normalize("NFKD", full_name or "")
        ascii_name = normalized.encode("ascii", "ignore").decode("ascii").lower()
        ascii_name = re.sub(r"[^a-z0-9]+", "_", ascii_name).strip("_")
        if ascii_name:
            return f"teacher_{ascii_name}"[:130]
        return f"teacher_{index:03d}"

    def _unique_username(self, base_username):
        User = get_user_model()
        username = base_username
        suffix = 1
        while User.objects.filter(username=username).exists():
            suffix += 1
            username = f"{base_username}_{suffix}"
        return username
