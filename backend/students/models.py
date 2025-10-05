from django.db import models
from django.contrib.auth import get_user_model
import uuid
from django.urls import reverse

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
        verbose_name="ولي الأمر"
    )
    parent_phone = models.CharField(max_length=20, blank=True, verbose_name="هاتف ولي الأمر")
    address = models.TextField(blank=True, verbose_name="العنوان")
    grade = models.CharField(max_length=50, blank=True, verbose_name="الصف")
    previous_memorization_amount = models.PositiveIntegerField(
        default=0,
        verbose_name="كمية الحفظ السابقة",
        help_text="عدد الآيات أو الأجزاء المحفوظة قبل الانضمام"
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
        verbose_name="أنشئ بواسطة"
    )

    class Meta:
        verbose_name = "طالب"
        verbose_name_plural = "الطلاب"
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_current_halaqa(self):
        """الحصول على الحلقة النشطة للطالب"""
        from halaqas.models import HalaqaMembership  # استيراد مؤجل هنا لتجنب الدائرية
        membership = HalaqaMembership.objects.filter(
            student=self,
            is_active=True
        ).first()
        return membership.halaqa if membership else None

    def get_access_link(self, request):
        return request.build_absolute_uri(
            reverse('student-retrieve', args=[str(self.access_token)]))




class MemorizationRecord(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='memorization_records',
        verbose_name="الطالب"
    )
    surah = models.CharField(max_length=100, verbose_name="السورة")
    from_verse = models.PositiveIntegerField(verbose_name="من آية")
    to_verse = models.PositiveIntegerField(verbose_name="إلى آية")
    date = models.DateField(auto_now_add=True, verbose_name="تاريخ التسجيل")
    is_approved = models.BooleanField(default=False, verbose_name="موافق عليه")
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="وافق عليه"
    )

    class Meta:
        verbose_name = "سجل حفظ"
        verbose_name_plural = "سجلات الحفظ"
        ordering = ['-date']

    def __str__(self):
        return f"{self.surah} ({self.from_verse}-{self.to_verse})"

    @property
    def verses_count(self):
        """عدد الآيات في هذا السجل"""
        return (self.to_verse - self.from_verse) + 1