from rest_framework import serializers
from datetime import datetime, time as datetime_time
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import (
    Category,
    Teacher,
    Halaqa,
    HalaqaMembership,
    Session,
    Attendance,
    PointTransaction,
    Plan,
    Homework,
)
from students.models import Student

User = get_user_model()

class TeacherSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    current_halaqa = serializers.PrimaryKeyRelatedField(queryset=Halaqa.objects.all(), allow_null=True, required=False)
    
    class Meta:
        model = Teacher
        fields = ['user', 'full_name', 'phone', 'qualification', 'join_date', 'current_halaqa']
        read_only_fields = ['join_date']

class HalaqaSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        allow_null=True,
        required=False,
    )
    teachers = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Teacher.objects.all()
    )
    category_details = serializers.SerializerMethodField()
    teachers_details = serializers.SerializerMethodField()
    active_students_count = serializers.SerializerMethodField()

    class Meta:
        model = Halaqa
        fields = [
            'id',
            'name',
            'category',
            'category_details',
            'teachers',
            'teachers_details',
            'join_code',
            'shareable_link',
            'is_active',
            'active_students_count',
        ]
        read_only_fields = [
            'join_code',
            'shareable_link',
            'category_details',
            'teachers_details',
            'active_students_count',
        ]

    def get_category_details(self, obj):
        if not obj.category_id:
            return None
        return {
            'id': obj.category_id,
            'code': obj.category.code,
            'name': obj.category.name,
            'grade_span': obj.category.grade_span,
        }

    def get_teachers_details(self, obj):
        return [
            {'id': t.id, 'name': t.full_name}
            for t in obj.teachers.all()
        ]

    def get_active_students_count(self, obj):
        return obj.members.filter(is_active=True).count()

class SessionSerializer(serializers.ModelSerializer):
    halaqa = serializers.PrimaryKeyRelatedField(queryset=Halaqa.objects.all())
    
    class Meta:
        model = Session
        fields = ['id', 'halaqa', 'date', 'start_time', 'end_time', 'notes']

class AttendanceSerializer(serializers.ModelSerializer):
    session = serializers.PrimaryKeyRelatedField(queryset=Session.objects.all())
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    
    class Meta:
        model = Attendance
        fields = ['id', 'session', 'student', 'status', 'notes']

class PointTransactionSerializer(serializers.ModelSerializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    halaqa = serializers.PrimaryKeyRelatedField(queryset=Halaqa.objects.all())
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    action_date = serializers.DateField(write_only=True, required=False)
    
    class Meta:
        model = PointTransaction
        fields = ['id', 'student', 'halaqa', 'value', 'balance_after', 'reason', 'date', 'created_by', 'action_date']
        read_only_fields = ['balance_after', 'date', 'created_by']

    def create(self, validated_data):
        action_date = validated_data.pop('action_date', None)
        if action_date:
            validated_data['date'] = timezone.make_aware(
                datetime.combine(action_date, datetime_time(hour=12, minute=0)),
                timezone.get_current_timezone(),
            )
        return super().create(validated_data)

class PlanSerializer(serializers.ModelSerializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    halaqa = serializers.PrimaryKeyRelatedField(queryset=Halaqa.objects.all())
    
    class Meta:
        model = Plan
        fields = ['id', 'student', 'halaqa', 'start_date', 'end_date', 'target', 'is_completed', 'notes']


class HomeworkSerializer(serializers.ModelSerializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    halaqa = serializers.PrimaryKeyRelatedField(queryset=Halaqa.objects.all())
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    evaluated_by = serializers.PrimaryKeyRelatedField(read_only=True)
    assignment_type_label = serializers.CharField(source='get_assignment_type_display', read_only=True)
    evaluation_label = serializers.CharField(source='get_evaluation_display', read_only=True)

    class Meta:
        model = Homework
        fields = [
            'id',
            'student',
            'halaqa',
            'assigned_date',
            'assignment_type',
            'assignment_type_label',
            'assignment_text',
            'assignment_notes',
            'evaluation_date',
            'evaluation',
            'evaluation_label',
            'evaluation_notes',
            'created_by',
            'evaluated_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'assignment_type_label',
            'evaluation_label',
            'created_by',
            'evaluated_by',
            'created_at',
            'updated_at',
        ]

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)

        student = attrs.get('student') or getattr(instance, 'student', None)
        halaqa = attrs.get('halaqa') or getattr(instance, 'halaqa', None)
        assigned_date = attrs.get('assigned_date') or getattr(instance, 'assigned_date', None)
        assignment_text = attrs.get('assignment_text', getattr(instance, 'assignment_text', ''))
        evaluation = attrs.get('evaluation', getattr(instance, 'evaluation', ''))
        evaluation_date = attrs.get('evaluation_date', getattr(instance, 'evaluation_date', None))

        if assignment_text is not None:
            assignment_text = assignment_text.strip()
            attrs['assignment_text'] = assignment_text
        if not assignment_text:
            raise serializers.ValidationError({'assignment_text': 'يرجى كتابة الواجب بشكل مختصر.'})

        if evaluation and not evaluation_date:
            raise serializers.ValidationError({'evaluation_date': 'تاريخ التقييم مطلوب عند تسجيل التقييم.'})
        if evaluation_date and not evaluation:
            raise serializers.ValidationError({'evaluation': 'يرجى اختيار نتيجة التقييم.'})
        if assigned_date and evaluation_date and evaluation_date < assigned_date:
            raise serializers.ValidationError({'evaluation_date': 'تاريخ التقييم يجب أن يكون بعد تاريخ الإسناد.'})

        if student and halaqa and not evaluation_date:
            pending_exists = Homework.objects.filter(
                student=student,
                halaqa=halaqa,
                evaluation_date__isnull=True,
            ).exclude(pk=getattr(instance, 'pk', None)).exists()
            if pending_exists:
                raise serializers.ValidationError('يوجد واجب آخر بانتظار التقييم لهذا الطالب.')

        return attrs
