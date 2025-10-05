from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import (
    Teacher, Halaqa, HalaqaMembership, 
    Session, Attendance, PointTransaction, Plan
)
from students.models import Student

User = get_user_model()

class TeacherSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    
    class Meta:
        model = Teacher
        fields = ['user', 'full_name', 'phone', 'qualification', 'join_date']
        read_only_fields = ['join_date']

class HalaqaSerializer(serializers.ModelSerializer):
    teachers = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Teacher.objects.all()
    )
    teachers_details = serializers.SerializerMethodField()
    active_students_count = serializers.SerializerMethodField()

    class Meta:
        model = Halaqa
        fields = [
            'id',
            'name',
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
            'teachers_details',
            'active_students_count',
        ]

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
    
    class Meta:
        model = PointTransaction
        fields = ['id', 'student', 'halaqa', 'value', 'balance_after', 'reason', 'date', 'created_by']
        read_only_fields = ['balance_after', 'date', 'created_by']

class PlanSerializer(serializers.ModelSerializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    halaqa = serializers.PrimaryKeyRelatedField(queryset=Halaqa.objects.all())
    
    class Meta:
        model = Plan
        fields = ['id', 'student', 'halaqa', 'start_date', 'end_date', 'target', 'is_completed', 'notes']