import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone


User = get_user_model()


class Student(models.Model):
    name = models.CharField(max_length=100, verbose_name="اسم الطالب")
    birth_date = models.DateField(verbose_name="تاريخ الميلاد")
    parent = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children',
        verbose_name="ولي الأمر",
    )
    parent_phone = models.CharField(max_length=20, blank=True, verbose_name="هاتف ولي الأمر")
    address = models.TextField(blank=True, verbose_name="العنوان")
    grade = models.CharField(max_length=50, blank=True, verbose_name="الصف")
    category = models.ForeignKey(
        'halaqas.Category',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='students',
        verbose_name="الفئة",
    )
    halaqa = models.ForeignKey(
        'halaqas.Halaqa',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_students',
        verbose_name="الحلقة الحالية",
    )
    previous_memorization_amount = models.PositiveIntegerField(
        default=0,
        verbose_name="كمية الحفظ السابقة",
        help_text="عدد الآيات أو الأجزاء المحفوظة قبل الانضمام",
    )
    access_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    enrollment_date = models.DateField(null=True, blank=True, verbose_name="تاريخ التسجيل")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_students',
        verbose_name="أُنشئ بواسطة",
    )

    class Meta:
        verbose_name = "طالب"
        verbose_name_plural = "الطلاب"
        ordering = ['name']

    def __str__(self):
        return self.name

    def clean(self):
        if self.halaqa_id and self.category_id and self.halaqa and self.halaqa.category_id:
            if self.halaqa.category_id != self.category_id:
                raise ValidationError("يجب أن تنتمي فئة الطالب إلى نفس فئة الحلقة الحالية")

    def save(self, *args, **kwargs):
        if self.halaqa_id and self.halaqa and self.halaqa.category_id and not self.category_id:
            self.category_id = self.halaqa.category_id
        if not self.category_id:
            from halaqas.models import Category

            category_code = Category.infer_code_from_grade(self.grade)
            if category_code:
                self.category_id = Category.objects.filter(code=category_code).values_list("id", flat=True).first()
        self.full_clean()
        super().save(*args, **kwargs)

    def get_current_halaqa(self):
        if self.halaqa_id:
            return self.halaqa

        from halaqas.models import HalaqaMembership

        membership = HalaqaMembership.objects.filter(
            student=self,
            is_active=True,
        ).order_by('-join_date', '-id').first()
        return membership.halaqa if membership else None

    def get_category_label(self):
        if self.category_id:
            return self.category.name

        from halaqas.models import infer_category_name_from_grade

        return infer_category_name_from_grade(self.grade)

    def get_access_link(self, request):
        return request.build_absolute_uri(
            reverse('students:students_data', args=[str(self.access_token)])
        )


class MemorizationRecord(models.Model):
    EVALUATION_CHOICES = (
        ('excellent', 'ممتاز'),
        ('very_good', 'جيد جدًا'),
        ('good', 'جيد'),
        ('needs_followup', 'يحتاج متابعة'),
    )

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='memorization_records',
        verbose_name="الطالب",
    )
    surah = models.CharField(max_length=100, verbose_name="السورة")
    from_verse = models.PositiveIntegerField(verbose_name="من آية")
    to_verse = models.PositiveIntegerField(verbose_name="إلى آية")
    date = models.DateField(default=timezone.localdate, verbose_name="تاريخ التسجيل")
    evaluation = models.CharField(
        max_length=20,
        choices=EVALUATION_CHOICES,
        blank=True,
        verbose_name="تقييم التسميع",
    )
    is_approved = models.BooleanField(default=False, verbose_name="موافق عليه")
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="وافق عليه",
    )

    class Meta:
        verbose_name = "سجل حفظ"
        verbose_name_plural = "سجلات الحفظ"
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.surah} ({self.from_verse}-{self.to_verse})"

    @property
    def verses_count(self):
        return (self.to_verse - self.from_verse) + 1
