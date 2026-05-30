import re
import secrets

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone


ARABIC_DIGIT_TRANSLATION = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

OFFICIAL_CATEGORY_SPECS = {
    "1": {
        "name": "الفئة 1",
        "grade_span": "الصفوف 1، 2، 3",
        "display_order": 1,
        "is_special": False,
    },
    "2": {
        "name": "الفئة 2",
        "grade_span": "الصفوف 4، 5",
        "display_order": 2,
        "is_special": False,
    },
    "3": {
        "name": "الفئة 3",
        "grade_span": "الصفوف 6، 7",
        "display_order": 3,
        "is_special": False,
    },
    "4": {
        "name": "الفئة 4",
        "grade_span": "الصف 8",
        "display_order": 4,
        "is_special": False,
    },
    "5": {
        "name": "الفئة 5",
        "grade_span": "الصفوف 9، 10، 11",
        "display_order": 5,
        "is_special": False,
    },
    "S": {
        "name": "الفئة S",
        "grade_span": "المرحلة الجامعية",
        "display_order": 6,
        "is_special": True,
    },
}

GRADE_KEYWORD_MAP = {
    1: ["1", "الأول", "اول", "أولى", "اولى", "first"],
    2: ["2", "الثاني", "ثاني", "second"],
    3: ["3", "الثالث", "ثالث", "third"],
    4: ["4", "الرابع", "رابع", "fourth"],
    5: ["5", "الخامس", "خامس", "fifth"],
    6: ["6", "السادس", "سادس", "sixth"],
    7: ["7", "السابع", "سابع", "seventh"],
    8: ["8", "الثامن", "ثامن", "eighth"],
    9: ["9", "التاسع", "تاسع", "ninth"],
    10: ["10", "العاشر", "عاشر", "tenth"],
    11: ["11", "الحادي عشر", "حادي عشر", "الحادى عشر", "eleventh"],
}

UNIVERSITY_KEYWORDS = ["جامعة", "جامعي", "جامعية", "university", "college"]


def normalize_grade_text(grade_value):
    return (grade_value or "").strip().lower().translate(ARABIC_DIGIT_TRANSLATION)


def extract_grade_number(grade_value):
    normalized = normalize_grade_text(grade_value)
    number_match = re.findall(r"\d+", normalized)
    if number_match:
        number = int(number_match[0])
        if 1 <= number <= 11:
            return number

    for number, keywords in GRADE_KEYWORD_MAP.items():
        if any(keyword in normalized for keyword in keywords):
            return number
    return None


def infer_category_code_from_grade(grade_value):
    normalized = normalize_grade_text(grade_value)
    if any(keyword in normalized for keyword in UNIVERSITY_KEYWORDS):
        return "S"

    grade_number = extract_grade_number(grade_value)
    if grade_number in {1, 2, 3}:
        return "1"
    if grade_number in {4, 5}:
        return "2"
    if grade_number in {6, 7}:
        return "3"
    if grade_number == 8:
        return "4"
    if grade_number in {9, 10, 11}:
        return "5"
    return None


def infer_category_name_from_grade(grade_value):
    category_code = infer_category_code_from_grade(grade_value)
    if not category_code:
        return "غير مصنف"
    return OFFICIAL_CATEGORY_SPECS[category_code]["name"]


class Category(models.Model):
    code = models.CharField(max_length=2, unique=True, verbose_name="رمز الفئة")
    name = models.CharField(max_length=50, unique=True, verbose_name="اسم الفئة")
    grade_span = models.CharField(max_length=80, verbose_name="نطاق الصفوف")
    display_order = models.PositiveSmallIntegerField(default=0, verbose_name="ترتيب العرض")
    is_special = models.BooleanField(default=False, verbose_name="فئة خاصة")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    class Meta:
        ordering = ["display_order", "code"]
        verbose_name = "فئة"
        verbose_name_plural = "الفئات"

    def __str__(self):
        return self.name

    @classmethod
    def seed_official_categories(cls):
        categories = []
        for code, spec in OFFICIAL_CATEGORY_SPECS.items():
            category, _ = cls.objects.get_or_create(
                code=code,
                defaults=spec,
            )
            categories.append(category)
        return categories

    @classmethod
    def infer_code_from_grade(cls, grade_value):
        return infer_category_code_from_grade(grade_value)

    @classmethod
    def infer_name_from_grade(cls, grade_value):
        return infer_category_name_from_grade(grade_value)


class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    qualification = models.CharField(max_length=100, blank=True)
    join_date = models.DateField(auto_now_add=True)
    current_halaqa = models.ForeignKey(
        "Halaqa",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_teachers",
        verbose_name="الحلقة الحالية",
    )

    def __str__(self):
        return self.full_name


class Halaqa(models.Model):
    name = models.CharField(max_length=100, unique=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="halaqas",
        verbose_name="الفئة",
    )
    teachers = models.ManyToManyField(Teacher, related_name="halaqas", blank=True)
    join_code = models.CharField(max_length=10, unique=True, blank=True)
    shareable_link = models.CharField(max_length=50, unique=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "حلقة"
        verbose_name_plural = "الحلقات"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.join_code:
            self.join_code = self._generate_join_code()
        if not self.shareable_link:
            self.shareable_link = self._generate_shareable_link()
        super().save(*args, **kwargs)

    def _generate_join_code(self):
        return "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))

    def _generate_shareable_link(self):
        return secrets.token_urlsafe(16)

    def get_absolute_url(self):
        return reverse("halaqa-share", kwargs={"link_code": self.shareable_link})


class TeacherAssignment(models.Model):
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    halaqa = models.ForeignKey(
        Halaqa,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
    )
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date", "-id"]
        verbose_name = "نقل/إسناد معلم"
        verbose_name_plural = "نقلات وإسنادات المعلمين"
        constraints = [
            models.UniqueConstraint(
                fields=["teacher"],
                condition=Q(is_active=True),
                name="unique_active_teacher_assignment_per_teacher",
            ),
        ]

    def __str__(self):
        return f"{self.teacher.full_name} في {self.halaqa.name}"

    def clean(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError("تاريخ الانتهاء يجب أن يكون بعد تاريخ البداية")


class HalaqaMembership(models.Model):
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="halaqa_memberships",
    )
    halaqa = models.ForeignKey(
        Halaqa,
        on_delete=models.CASCADE,
        related_name="members",
    )
    join_date = models.DateField(auto_now_add=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("student", "halaqa")
        ordering = ["-join_date"]
        verbose_name = "عضوية الحلقة"
        verbose_name_plural = "عضويات الحلقات"
        constraints = [
            models.UniqueConstraint(
                fields=["student"],
                condition=Q(is_active=True),
                name="unique_active_halaqa_membership_per_student",
            ),
        ]

    def clean(self):
        if self.end_date and self.join_date and self.end_date < self.join_date:
            raise ValidationError("تاريخ الانتهاء يجب أن يكون بعد تاريخ البداية")

    def save(self, *args, **kwargs):
        transition_date = self.join_date or timezone.localdate()
        with transaction.atomic():
            if self.is_active and self.student_id:
                active_memberships = HalaqaMembership.objects.filter(
                    student_id=self.student_id,
                    is_active=True,
                ).exclude(pk=self.pk)
                active_memberships.filter(end_date__isnull=True).update(end_date=transition_date)
                active_memberships.update(is_active=False)
            self.full_clean()
            super().save(*args, **kwargs)
        self._sync_student_snapshot()

    def _resolve_category_id(self):
        if self.halaqa.category_id:
            return self.halaqa.category_id

        category_id = getattr(self.student, "category_id", None)
        if not category_id:
            category_code = Category.infer_code_from_grade(getattr(self.student, "grade", ""))
            if category_code:
                category_id = Category.objects.filter(code=category_code).values_list("id", flat=True).first()

        if category_id:
            Halaqa.objects.filter(pk=self.halaqa_id, category_id__isnull=True).update(category_id=category_id)
            self.halaqa.category_id = category_id
        return category_id

    def _sync_student_snapshot(self):
        from students.models import Student

        current_category_id = self._resolve_category_id()
        if self.is_active:
            Student.objects.filter(pk=self.student_id).update(
                halaqa_id=self.halaqa_id,
                category_id=current_category_id,
            )
            return

        next_membership = (
            HalaqaMembership.objects.filter(student_id=self.student_id, is_active=True)
            .select_related("halaqa__category")
            .order_by("-join_date", "-id")
            .first()
        )
        if next_membership:
            next_category_id = next_membership._resolve_category_id()
            Student.objects.filter(pk=self.student_id).update(
                halaqa_id=next_membership.halaqa_id,
                category_id=next_category_id,
            )
            return

        Student.objects.filter(pk=self.student_id, halaqa_id=self.halaqa_id).update(
            halaqa_id=None,
        )

    def __str__(self):
        if getattr(self, "student_id", None):
            try:
                return f"{self.student.name} في {self.halaqa.name}"
            except Exception:
                return f"عضوية #{self.pk}"
        return "عضوية جديدة"


class Session(models.Model):
    halaqa = models.ForeignKey(
        Halaqa,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date"]
        unique_together = ("halaqa", "date")


class Attendance(models.Model):
    RECORDED_BY_ROLE_CHOICES = (
        ("teacher", "أستاذ"),
        ("supervisor", "موجه"),
        ("admin", "أدمن"),
    )

    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name="attendances",
    )
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="attendances",
    )
    status = models.CharField(
        max_length=20,
        choices=(
            ("present", "حاضر"),
            ("absent", "غائب"),
            ("excused", "معذور"),
        ),
    )
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_attendances",
    )
    recorded_by_role = models.CharField(
        max_length=20,
        choices=RECORDED_BY_ROLE_CHOICES,
        blank=True,
        default="",
    )

    class Meta:
        unique_together = ("session", "student")


class PointTransaction(models.Model):
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="point_transactions",
    )
    halaqa = models.ForeignKey(Halaqa, on_delete=models.CASCADE)
    value = models.IntegerField()
    balance_after = models.IntegerField(editable=False)
    reason = models.TextField()
    date = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            last_balance = self.student.point_transactions.aggregate(models.Sum("value"))["value__sum"] or 0
            self.balance_after = last_balance + self.value
        super().save(*args, **kwargs)


class Plan(models.Model):
    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="plans",
    )
    halaqa = models.ForeignKey(Halaqa, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    target = models.TextField()
    is_completed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError("تاريخ الانتهاء يجب أن يكون بعد تاريخ البداية")


class Homework(models.Model):
    ASSIGNMENT_TYPE_CHOICES = (
        ("surah", "سورة"),
        ("pages", "صفحات"),
        ("text", "واجب نصي"),
    )

    EVALUATION_CHOICES = (
        ("excellent", "متقن"),
        ("completed", "منجز"),
        ("partial", "منجز جزئياً"),
        ("not_completed", "غير منجز"),
    )

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="homeworks",
    )
    halaqa = models.ForeignKey(
        Halaqa,
        on_delete=models.CASCADE,
        related_name="homeworks",
    )
    assigned_date = models.DateField(default=timezone.localdate)
    assignment_type = models.CharField(max_length=20, choices=ASSIGNMENT_TYPE_CHOICES)
    assignment_text = models.CharField(max_length=120)
    pages = models.CharField(max_length=80, blank=True)
    surah = models.CharField(max_length=100, blank=True)
    from_verse = models.PositiveIntegerField(null=True, blank=True)
    to_verse = models.PositiveIntegerField(null=True, blank=True)
    assignment_notes = models.CharField(max_length=255, blank=True)
    expected_recitation_date = models.DateField(null=True, blank=True)
    evaluation_date = models.DateField(null=True, blank=True)
    evaluation = models.CharField(max_length=20, choices=EVALUATION_CHOICES, blank=True)
    evaluation_notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_homeworks",
    )
    evaluated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluated_homeworks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-assigned_date", "-id"]

    def clean(self):
        if self.expected_recitation_date and self.expected_recitation_date < self.assigned_date:
            raise ValidationError("تاريخ التسميع المتوقع يجب أن يكون بعد تاريخ إسناد الواجب")
        if self.from_verse is not None and self.to_verse is not None and self.to_verse < self.from_verse:
            raise ValidationError("رقم الآية الأخيرة يجب أن يكون أكبر من أو يساوي الآية الأولى")
        if self.evaluation and not self.evaluation_date:
            raise ValidationError("تاريخ التقييم مطلوب عند تسجيل تقييم الواجب")
        if self.evaluation_date and not self.evaluation:
            raise ValidationError("يجب اختيار تقييم عند إدخال تاريخ التقييم")
        if self.evaluation_date and self.evaluation_date < self.assigned_date:
            raise ValidationError("تاريخ التقييم يجب أن يكون بعد تاريخ إسناد الواجب")

    def __str__(self):
        return f"{self.student.name} - {self.assignment_text}"


def _synchronize_teacher_assignment(teacher_id, halaqa_id):
    through_model = Halaqa.teachers.through
    today = timezone.localdate()

    if halaqa_id:
        through_model.objects.filter(teacher_id=teacher_id).exclude(halaqa_id=halaqa_id).delete()
        through_model.objects.get_or_create(teacher_id=teacher_id, halaqa_id=halaqa_id)
        Teacher.objects.filter(pk=teacher_id).update(current_halaqa_id=halaqa_id)

        TeacherAssignment.objects.filter(teacher_id=teacher_id, is_active=True).exclude(
            halaqa_id=halaqa_id
        ).update(
            is_active=False,
            end_date=today,
        )

        active_assignment = TeacherAssignment.objects.filter(
            teacher_id=teacher_id,
            halaqa_id=halaqa_id,
            is_active=True,
        ).first()
        if not active_assignment:
            TeacherAssignment.objects.create(
                teacher_id=teacher_id,
                halaqa_id=halaqa_id,
                start_date=today,
                is_active=True,
            )
        return

    through_model.objects.filter(teacher_id=teacher_id).delete()
    Teacher.objects.filter(pk=teacher_id).update(current_halaqa_id=None)
    TeacherAssignment.objects.filter(teacher_id=teacher_id, is_active=True).update(
        is_active=False,
        end_date=today,
    )


@receiver(post_save, sender=Teacher)
def synchronize_teacher_current_halaqa(sender, instance, **kwargs):
    if instance.current_halaqa_id:
        _synchronize_teacher_assignment(instance.pk, instance.current_halaqa_id)
        return

    remaining_link = Halaqa.teachers.through.objects.filter(teacher_id=instance.pk).order_by("-id").first()
    _synchronize_teacher_assignment(instance.pk, remaining_link.halaqa_id if remaining_link else None)


@receiver(m2m_changed, sender=Halaqa.teachers.through)
def synchronize_teacher_legacy_membership(sender, instance, action, reverse, model, pk_set, **kwargs):
    if action == "pre_clear":
        if reverse:
            instance._halaqa_ids_before_clear = list(instance.halaqas.values_list("pk", flat=True))
        else:
            instance._teacher_ids_before_clear = list(instance.teachers.values_list("pk", flat=True))
        return

    if action == "post_add":
        if reverse:
            selected_halaqa_id = sorted(pk_set)[-1] if pk_set else instance.current_halaqa_id
            if selected_halaqa_id:
                _synchronize_teacher_assignment(instance.pk, selected_halaqa_id)
            return

        for teacher_id in pk_set:
            _synchronize_teacher_assignment(teacher_id, instance.pk)
        return

    if action == "post_remove":
        if reverse:
            remaining_link = sender.objects.filter(teacher_id=instance.pk).order_by("-id").first()
            _synchronize_teacher_assignment(instance.pk, remaining_link.halaqa_id if remaining_link else None)
            return

        for teacher_id in pk_set:
            remaining_link = sender.objects.filter(teacher_id=teacher_id).order_by("-id").first()
            _synchronize_teacher_assignment(teacher_id, remaining_link.halaqa_id if remaining_link else None)
        return

    if action == "post_clear":
        if reverse:
            _synchronize_teacher_assignment(instance.pk, None)
            return

        for teacher_id in getattr(instance, "_teacher_ids_before_clear", []):
            remaining_link = sender.objects.filter(teacher_id=teacher_id).order_by("-id").first()
            _synchronize_teacher_assignment(teacher_id, remaining_link.halaqa_id if remaining_link else None)
