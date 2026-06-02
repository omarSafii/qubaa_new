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
from students.models import MemorizationRecord, Student

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
    recorded_by = serializers.PrimaryKeyRelatedField(read_only=True)
    recorded_by_role = serializers.CharField(read_only=True)
    
    class Meta:
        model = Attendance
        fields = ['id', 'session', 'student', 'status', 'notes', 'recorded_by', 'recorded_by_role']

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
    linked_recitation_id = serializers.SerializerMethodField()
    create_recitation_record = serializers.BooleanField(write_only=True, required=False, default=False)
    recitation_date = serializers.DateField(write_only=True, required=False, allow_null=True)
    recitation_pages = serializers.CharField(write_only=True, required=False, allow_blank=True)
    recitation_surah = serializers.CharField(write_only=True, required=False, allow_blank=True)
    recitation_from_verse = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    recitation_to_verse = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    recitation_evaluation = serializers.ChoiceField(
        choices=MemorizationRecord.EVALUATION_CHOICES,
        write_only=True,
        required=False,
        allow_blank=True,
    )
    recitation_notes = serializers.CharField(write_only=True, required=False, allow_blank=True)

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
            'pages',
            'surah',
            'from_verse',
            'to_verse',
            'assignment_notes',
            'expected_recitation_date',
            'evaluation_date',
            'evaluation',
            'evaluation_label',
            'evaluation_notes',
            'linked_recitation_id',
            'create_recitation_record',
            'recitation_date',
            'recitation_pages',
            'recitation_surah',
            'recitation_from_verse',
            'recitation_to_verse',
            'recitation_evaluation',
            'recitation_notes',
            'created_by',
            'evaluated_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'assignment_type_label',
            'evaluation_label',
            'linked_recitation_id',
            'created_by',
            'evaluated_by',
            'created_at',
            'updated_at',
        ]
        extra_kwargs = {
            'assignment_text': {'required': False, 'allow_blank': True},
            'pages': {'required': False, 'allow_blank': True},
            'surah': {'required': False, 'allow_blank': True},
            'from_verse': {'required': False, 'allow_null': True},
            'to_verse': {'required': False, 'allow_null': True},
        }

    def get_linked_recitation_id(self, obj):
        linked_record = obj.memorization_records.order_by('-date', '-id').first()
        return linked_record.id if linked_record else None

    def _build_assignment_text(self, attrs, instance=None):
        assignment_type = attrs.get('assignment_type') or getattr(instance, 'assignment_type', '')
        pages = (attrs.get('pages', getattr(instance, 'pages', '')) or '').strip()
        surah = (attrs.get('surah', getattr(instance, 'surah', '')) or '').strip()
        from_verse = attrs.get('from_verse', getattr(instance, 'from_verse', None))
        to_verse = attrs.get('to_verse', getattr(instance, 'to_verse', None))

        if assignment_type == 'pages' and pages:
            return f'الصفحات {pages}'
        if assignment_type == 'surah' and surah:
            if from_verse is not None and to_verse is not None:
                return f'سورة {surah} {from_verse}-{to_verse}'
            return f'سورة {surah}'
        return ''

    def _recitation_defaults(self, instance, recitation_payload):
        homework_to_memorization_evaluation = {
            'excellent': 'excellent',
            'completed': 'very_good',
            'partial': 'good',
            'not_completed': 'needs_followup',
        }
        return {
            'student': instance.student,
            'halaqa': instance.halaqa,
            'homework': instance,
            'recitation_type': 'homework',
            'date': recitation_payload.get('recitation_date') or instance.evaluation_date,
            'pages': (recitation_payload.get('recitation_pages') or instance.pages or '').strip(),
            'surah': (recitation_payload.get('recitation_surah') or instance.surah or '').strip(),
            'from_verse': recitation_payload.get('recitation_from_verse') if recitation_payload.get('recitation_from_verse') is not None else instance.from_verse,
            'to_verse': recitation_payload.get('recitation_to_verse') if recitation_payload.get('recitation_to_verse') is not None else instance.to_verse,
            'evaluation': (
                recitation_payload.get('recitation_evaluation')
                or homework_to_memorization_evaluation.get(instance.evaluation, '')
            ),
            'notes': (recitation_payload.get('recitation_notes') or instance.evaluation_notes or '').strip(),
            'is_approved': True,
        }

    def _pop_recitation_payload(self, validated_data):
        field_names = [
            'create_recitation_record',
            'recitation_date',
            'recitation_pages',
            'recitation_surah',
            'recitation_from_verse',
            'recitation_to_verse',
            'recitation_evaluation',
            'recitation_notes',
        ]
        return {field_name: validated_data.pop(field_name, None) for field_name in field_names}

    def _save_homework_recitation(self, instance, recitation_payload):
        defaults = self._recitation_defaults(instance, recitation_payload)
        user = None
        request = self.context.get('request')
        if request and getattr(request.user, 'is_authenticated', False):
            user = request.user
        if user:
            defaults['created_by'] = user
            defaults['approved_by'] = user

        record = instance.memorization_records.filter(recitation_type='homework').order_by('-date', '-id').first()
        if record:
            for field_name, value in defaults.items():
                setattr(record, field_name, value)
            record.save()
            return record
        return MemorizationRecord.objects.create(**defaults)

    def validate(self, attrs):
        instance = getattr(self, 'instance', None)

        student = attrs.get('student') or getattr(instance, 'student', None)
        halaqa = attrs.get('halaqa') or getattr(instance, 'halaqa', None)
        assigned_date = attrs.get('assigned_date') or getattr(instance, 'assigned_date', None)
        assignment_text = attrs.get('assignment_text', getattr(instance, 'assignment_text', ''))
        assignment_type = attrs.get('assignment_type') or getattr(instance, 'assignment_type', '')
        pages = (attrs.get('pages', getattr(instance, 'pages', '')) or '').strip()
        surah = (attrs.get('surah', getattr(instance, 'surah', '')) or '').strip()
        from_verse = attrs.get('from_verse', getattr(instance, 'from_verse', None))
        to_verse = attrs.get('to_verse', getattr(instance, 'to_verse', None))
        expected_recitation_date = attrs.get(
            'expected_recitation_date',
            getattr(instance, 'expected_recitation_date', None),
        )
        evaluation = attrs.get('evaluation', getattr(instance, 'evaluation', ''))
        evaluation_date = attrs.get('evaluation_date', getattr(instance, 'evaluation_date', None))
        create_recitation_record = attrs.get('create_recitation_record', False)

        if assignment_text is not None:
            assignment_text = assignment_text.strip()
            attrs['assignment_text'] = assignment_text
        if not assignment_text:
            assignment_text = self._build_assignment_text(attrs, instance)
            attrs['assignment_text'] = assignment_text
        if not assignment_text:
            raise serializers.ValidationError({'assignment_text': 'يرجى كتابة الواجب بشكل مختصر.'})
        if assignment_type == 'pages' and pages:
            attrs['pages'] = pages
        if assignment_type == 'surah' and surah:
            attrs['surah'] = surah
        if from_verse is not None and to_verse is not None and to_verse < from_verse:
            raise serializers.ValidationError({'to_verse': 'رقم الآية الأخيرة يجب أن يكون أكبر من أو يساوي الآية الأولى.'})
        if expected_recitation_date and assigned_date and expected_recitation_date < assigned_date:
            raise serializers.ValidationError({'expected_recitation_date': 'تاريخ التسميع المتوقع يجب أن يكون بعد تاريخ الإسناد.'})

        if evaluation and not evaluation_date:
            raise serializers.ValidationError({'evaluation_date': 'تاريخ التقييم مطلوب عند تسجيل التقييم.'})
        if evaluation_date and not evaluation:
            raise serializers.ValidationError({'evaluation': 'يرجى اختيار نتيجة التقييم.'})
        if assigned_date and evaluation_date and evaluation_date < assigned_date:
            raise serializers.ValidationError({'evaluation_date': 'تاريخ التقييم يجب أن يكون بعد تاريخ الإسناد.'})
        if create_recitation_record:
            recitation_pages = (
                attrs.get('recitation_pages')
                or attrs.get('pages')
                or getattr(instance, 'pages', '')
                or ''
            ).strip()
            recitation_surah = (
                attrs.get('recitation_surah')
                or attrs.get('surah')
                or getattr(instance, 'surah', '')
                or ''
            ).strip()
            recitation_from = attrs.get(
                'recitation_from_verse',
                attrs.get('from_verse', getattr(instance, 'from_verse', None)),
            )
            recitation_to = attrs.get(
                'recitation_to_verse',
                attrs.get('to_verse', getattr(instance, 'to_verse', None)),
            )
            if not recitation_pages and not recitation_surah:
                raise serializers.ValidationError({'recitation_surah': 'يرجى تحديد ما تم تسميعه فعلياً.'})
            if recitation_surah and not recitation_pages and (recitation_from is None or recitation_to is None):
                raise serializers.ValidationError({'recitation_from_verse': 'يرجى تحديد نطاق الآيات في التسميع.'})
            if recitation_from is not None and recitation_to is not None and recitation_to < recitation_from:
                raise serializers.ValidationError({'recitation_to_verse': 'رقم الآية الأخيرة يجب أن يكون أكبر من أو يساوي الآية الأولى.'})

        if student and halaqa and not evaluation_date:
            pending_exists = Homework.objects.filter(
                student=student,
                halaqa=halaqa,
                evaluation_date__isnull=True,
            ).exclude(pk=getattr(instance, 'pk', None)).exists()
            if pending_exists:
                raise serializers.ValidationError('على الطالب واجب غير منجز.')

        return attrs

    def create(self, validated_data):
        recitation_payload = self._pop_recitation_payload(validated_data)
        homework = super().create(validated_data)
        if recitation_payload.get('create_recitation_record') and homework.evaluation and homework.evaluation_date:
            self._save_homework_recitation(homework, recitation_payload)
        return homework

    def update(self, instance, validated_data):
        recitation_payload = self._pop_recitation_payload(validated_data)
        homework = super().update(instance, validated_data)
        if recitation_payload.get('create_recitation_record') and homework.evaluation and homework.evaluation_date:
            self._save_homework_recitation(homework, recitation_payload)
        return homework
