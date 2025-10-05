# halaqas/signals.py
import random
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from students.models import Student
from .models import Halaqa, HalaqaMembership

User = get_user_model()

@receiver(post_save, sender=Student)
def create_default_membership(sender, instance, created, **kwargs):
    """
    لما يُخلق Student جديد:
    - إذا أرسل عند التسجيل halaqa_id، بهترّف لعضويته هناك.
    - وإلا يروح لعضوية الحلقة الافتراضية.
    """
    if not created:
        return

    # إذا كان الـ student عنده relation إلى halaqa_fk (قد تكون أضفتها في StudentRegistrationSerializer)
    if hasattr(instance, 'halaqa') and instance.halaqa:
        HalaqaMembership.objects.create(
            student=instance,
            halaqa=instance.halaqa,
        )
        return

    # خلاف ذلك، استخدم الحلقة الافتراضية أو أنشئها
    default_code = 'DEFAULT'
    default_halaqa, _ = Halaqa.objects.get_or_create(
        join_code=default_code,
        defaults={'name': 'افتراضي'}
    )
    HalaqaMembership.objects.create(
        student=instance,
        halaqa=default_halaqa,
    )
