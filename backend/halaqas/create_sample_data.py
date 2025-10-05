# scripts/create_sample_data.py
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')
django.setup()

from halaqas.services import HalaqaManager
from accounts.models import User

def create_initial_data():
    # الحصول على المستخدم الأول أو إنشائه
    teacher, _ = User.objects.get_or_create(
        username='admin1',
        defaults={'is_staff': True, 'is_superuser': True}
    )
    
    # إنشاء الحلقة الافتتاحية
    halaqa = HalaqaManager.create_halaqa_with_template(
        name="الحلقة الافتتاحية",
        teacher=teacher
    )
    print(f"تم إنشاء الحلقة: {halaqa.name}")

if __name__ == "__main__":
    create_initial_data()