from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.urls import reverse
import secrets

class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    qualification = models.CharField(max_length=100, blank=True)
    join_date = models.DateField(auto_now_add=True)
    
    def __str__(self):
        return self.full_name

class Halaqa(models.Model):
    name = models.CharField(max_length=100, unique=True)
    teachers = models.ManyToManyField(Teacher, related_name='halaqas')
    join_code = models.CharField(max_length=10, unique=True, blank=True)
    shareable_link = models.CharField(max_length=50, unique=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.join_code:
            self.join_code = self._generate_join_code()
        if not self.shareable_link:
            self.shareable_link = self._generate_shareable_link()
        super().save(*args, **kwargs)
    
    def _generate_join_code(self):
        return ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))
    
    def _generate_shareable_link(self):
        return secrets.token_urlsafe(16)
    
    def get_absolute_url(self):
        return reverse('halaqa-share', kwargs={'link_code': self.shareable_link})

class HalaqaMembership(models.Model):
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='halaqa_memberships'
    )
    halaqa = models.ForeignKey(
        Halaqa,
        on_delete=models.CASCADE,
        related_name='members'
    )
    join_date = models.DateField(auto_now_add=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('student', 'halaqa')
        ordering = ['-join_date']
        verbose_name = 'عضوية الحلقة'
        verbose_name_plural = 'عضويات الحلقات'

    def clean(self):
        if (self.is_active and
            HalaqaMembership.objects
                .filter(student=self.student, is_active=True)
                .exclude(pk=self.pk)
                .exists()):
            raise ValidationError('الطالب لديه عضوية فعالة في حلقة أخرى')

    def __str__(self):
        if getattr(self, 'student_id', None):
            try:
                return f"{self.student.name} في {self.halaqa.name}"
            except:
                return f"عضوية #{self.pk}"
        return "عضوية جديدة"

class Session(models.Model):
    halaqa = models.ForeignKey(
        Halaqa,
        on_delete=models.CASCADE,
        related_name='sessions'
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-date']
        unique_together = ('halaqa', 'date')

class Attendance(models.Model):
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    status = models.CharField(
        max_length=20,
        choices=(
            ('present', 'حاضر'),
            ('absent', 'غائب'),
            ('excused', 'معذور')
        )
    )
    notes = models.TextField(blank=True)
    
    class Meta:
        unique_together = ('session', 'student')

class PointTransaction(models.Model):
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='point_transactions'
    )
    halaqa = models.ForeignKey(
        Halaqa,
        on_delete=models.CASCADE
    )
    value = models.IntegerField()
    balance_after = models.IntegerField(editable=False)
    reason = models.TextField()
    date = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True
    )
    
    def save(self, *args, **kwargs):
        if not self.pk:
            last_balance = self.student.point_transactions.aggregate(
                models.Sum('value')
            )['value__sum'] or 0
            self.balance_after = last_balance + self.value
        super().save(*args, **kwargs)

class Plan(models.Model):
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='plans'
    )
    halaqa = models.ForeignKey(
        Halaqa,
        on_delete=models.CASCADE
    )
    start_date = models.DateField()
    end_date = models.DateField()
    target = models.TextField()
    is_completed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    
    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError('تاريخ الانتهاء يجب أن يكون بعد تاريخ البداية')