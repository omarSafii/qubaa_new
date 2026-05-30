from django.contrib.auth.models import User
from django.db import models

class Profile(models.Model):
    ROLE_CHOICES = (
        ('parent', 'ولي أمر'),
        ('teacher', 'أستاذ'),
        ('supervisor', 'موجه'),
        ('admin', 'أدمن'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='parent')

    def __str__(self):
        return f"{self.user.username} - {self.role}"
