from django.db import transaction
from django.utils import timezone
from .models import Halaqa, HalaqaMembership
from students.models import Student

class HalaqaManager:
    @classmethod
    def create_halaqa_with_template(cls, name, teacher):
        """إنشاء حلقة جديدة مع طالب افتراضي"""
        with transaction.atomic():
            # 1. إنشاء الحلقة
            halaqa = Halaqa.objects.create(
                name=name,
                is_active=True
            )
            halaqa.teachers.add(teacher)
            
            # 2. إنشاء طالب افتراضي
            dummy_student = Student.objects.create(
                name="طالب افتراضي - " + name,
                birth_date=timezone.localdate(),
                parent_phone="0000000000"
            )
            
            # 3. الربط بينهما
            HalaqaMembership.objects.create(
                student=dummy_student,
                halaqa=halaqa,
                is_active=False  # غير فعال لعدم التشويش على الإحصائيات
            )
            
            return halaqa

    @classmethod
    def add_student_to_halaqa(cls, student_data, halaqa_id):
        """إضافة طالب جديد لحلقة موجودة"""
        from students.serializers import StudentRegistrationSerializer
        
        serializer = StudentRegistrationSerializer(data={
            **student_data,
            'halaqa_id': halaqa_id
        })
        
        if serializer.is_valid():
            return serializer.save()
        raise ValueError(serializer.errors)
