from rest_framework import serializers
from django.contrib.auth import get_user_model
from halaqas.models import Halaqa, HalaqaMembership # أضفنا استيراد HalaqaMembership
from students.models import Student,MemorizationRecord

User = get_user_model()

class StudentRegistrationSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    birth_date = serializers.DateField()
    halaqa_id = serializers.IntegerField(write_only=True)
    parent_name = serializers.CharField(max_length=150)
    parent_phone = serializers.CharField(max_length=20)
    address = serializers.CharField(allow_blank=True, required=False)
    grade = serializers.CharField(max_length=50, allow_blank=True, required=False)

    def validate_halaqa_id(self, value):
        """يتحقق من وجود الحلقة المحددة"""
        if not Halaqa.objects.filter(pk=value, is_active=True).exists():
            raise serializers.ValidationError("الحلقة غير موجودة أو غير مفعّلة")
        return value

    def create(self, validated_data):
        # 1) معالجة بيانات ولي الأمر
        phone = validated_data.pop('parent_phone')
        parent_name = validated_data.pop('parent_name')
        halaqa_id = validated_data.pop('halaqa_id')
        
        # 2) إنشاء/جلب حساب ولي الأمر
        user, created = User.objects.get_or_create(
            username=f"parent_{phone}",
            defaults={
                'first_name': parent_name,
                'password': User.objects.make_random_password()
            }
        )

        # 3) إنشاء سجل الطالب
        student = Student.objects.create(
            parent=user,
            parent_phone=phone,
            **validated_data
        )

        # 4) الربط مع الحلقة عبر HalaqaMembership
        HalaqaMembership.objects.create(
            student=student,
            halaqa_id=halaqa_id,
            is_active=True
        )

        return student

class StudentSerializer(serializers.ModelSerializer):
    current_halaqa = serializers.SerializerMethodField()  # حقل جديد لعرض الحلقة الحالية
    halaqa_details = serializers.SerializerMethodField()  # تفاصيل الحلقة

    class Meta:
        model = Student
        fields = [
            'id', 'name', 'birth_date', 'parent', 'parent_phone',
            'address', 'grade', 'access_token', 'current_halaqa',
            'halaqa_details', 'created_at'
        ]
        read_only_fields = [
            'access_token', 'created_by', 'created_at',
            'current_halaqa', 'halaqa_details'
        ]

    def get_current_halaqa(self, obj):
        """يحصل على معرف الحلقة النشطة للطالب"""
        membership = obj.halaqa_memberships.filter(is_active=True).first()
        return membership.halaqa.id if membership else None

    def get_halaqa_details(self, obj):
        """يحصل على تفاصيل الحلقة النشطة"""
        membership = obj.halaqa_memberships.filter(is_active=True).first()
        if membership:
            from halaqas.serializers import HalaqaSerializer  # استيراد هنا لتجنب التبعية الدائرية
            return HalaqaSerializer(membership.halaqa).data
        return None
    
    
class MemorizationRecordSerializer(serializers.ModelSerializer):
        student_name = serializers.CharField(source='student.name', read_only=True)
        approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)
        verses_count = serializers.ReadOnlyField()

        class Meta:
            model = MemorizationRecord
            fields = [
                'id', 'student', 'student_name', 'surah', 'from_verse', 'to_verse',
                'verses_count', 'date', 'is_approved', 'approved_by', 'approved_by_name'
            ]
            read_only_fields = ['verses_count', 'student_name', 'approved_by_name', 'date']