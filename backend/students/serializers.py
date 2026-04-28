from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.utils.crypto import get_random_string
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
        halaqa = Halaqa.objects.select_related('category').get(pk=halaqa_id)
        
        # 2) إنشاء/جلب حساب ولي الأمر
        user, created = User.objects.get_or_create(
            username=f"parent_{phone}",
            defaults={
                'first_name': parent_name,
                'password': make_password(get_random_string(12))
            }
        )

        # 3) إنشاء سجل الطالب
        student = Student.objects.create(
            parent=user,
            parent_phone=phone,
            halaqa=halaqa,
            category=halaqa.category,
            **validated_data
        )

        # 4) الربط مع الحلقة عبر HalaqaMembership
        HalaqaMembership.objects.create(
            student=student,
            halaqa=halaqa,
            is_active=True
        )

        return student

class StudentSerializer(serializers.ModelSerializer):
    current_halaqa = serializers.SerializerMethodField()  # حقل جديد لعرض الحلقة الحالية
    halaqa_details = serializers.SerializerMethodField()  # تفاصيل الحلقة
    category_label = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            'id', 'name', 'birth_date', 'parent', 'parent_phone',
            'address', 'grade', 'category', 'category_label', 'halaqa', 'access_token', 'current_halaqa',
            'halaqa_details', 'created_at'
        ]
        read_only_fields = [
            'access_token', 'created_by', 'created_at',
            'current_halaqa', 'halaqa_details', 'category_label', 'category', 'halaqa'
        ]

    def get_current_halaqa(self, obj):
        """يحصل على معرف الحلقة النشطة للطالب"""
        if obj.halaqa_id:
            return obj.halaqa_id
        membership = obj.halaqa_memberships.filter(is_active=True).order_by('-join_date', '-id').first()
        return membership.halaqa.id if membership else None

    def get_halaqa_details(self, obj):
        """يحصل على تفاصيل الحلقة النشطة"""
        halaqa = obj.halaqa or obj.get_current_halaqa()
        if halaqa:
            from halaqas.serializers import HalaqaSerializer  # استيراد هنا لتجنب التبعية الدائرية
            return HalaqaSerializer(halaqa).data
        return None

    def get_category_label(self, obj):
        return obj.get_category_label()
    
    
class MemorizationRecordSerializer(serializers.ModelSerializer):
        student_name = serializers.CharField(source='student.name', read_only=True)
        approved_by_name = serializers.CharField(source='approved_by.get_full_name', read_only=True)
        verses_count = serializers.ReadOnlyField()

        class Meta:
            model = MemorizationRecord
            fields = [
                'id', 'student', 'student_name', 'surah', 'from_verse', 'to_verse',
                'verses_count', 'date', 'evaluation', 'is_approved', 'approved_by', 'approved_by_name'
            ]
            read_only_fields = ['verses_count', 'student_name', 'approved_by_name']
            extra_kwargs = {
                'date': {'required': False},
            }
