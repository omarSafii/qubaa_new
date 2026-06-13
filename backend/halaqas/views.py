from collections import Counter, defaultdict
from datetime import time
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, ExpressionWrapper, F, FloatField, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from students.models import MemorizationRecord, Student
from students.serializers import StudentSerializer

from .access import role_for_user, user_can_access_halaqa
from .forms import HalaqaForm
from .models import (
    Attendance,
    Category,
    Halaqa,
    HalaqaMembership,
    Homework,
    Plan,
    PointTransaction,
    Session,
    SupervisorAttendanceShare,
    Teacher,
)
from .serializers import (
    AttendanceSerializer,
    HalaqaSerializer,
    HomeworkSerializer,
    PlanSerializer,
    PointTransactionSerializer as PointSerializer,
)


VERSE_COUNT_EXPR = ExpressionWrapper(
    F('to_verse') - F('from_verse') + Value(1),
    output_field=IntegerField(),
)

POINT_REASON_PRESETS = [
    'مشاركة مميزة',
    'إتقان التسميع',
    'انضباط وحضور',
    'مساعدة الزملاء',
    'تأخر',
    'غياب بدون عذر',
    'ملاحظة سلوكية',
]

ATTENDANCE_NOTE_PRESETS = [
    'بدون ملاحظات',
    'حضر في الوقت',
    'تأخر قليلًا',
    'انصرف مبكرًا',
    'تم إبلاغ ولي الأمر',
]

PLAN_TARGET_PRESETS = [
    'مراجعة المحفوظ الحالي',
    'حفظ مقطع جديد',
    'مراجعة مع تثبيت',
    'إتقان سورة محددة',
]

ATTENDANCE_STATUS_LABELS = {
    'present': 'حاضر',
    'absent': 'غائب',
    'excused': 'غياب مبرر',
}

ATTENDANCE_SOURCE_LABELS = {
    'teacher': 'المصدر: الأستاذ',
    'supervisor': 'المصدر: الموجه',
    'admin': 'المصدر: الإدارة',
}
ATTENDANCE_LOCKED_ROLES = {'teacher', 'supervisor'}


def _role_for_user(user):
    return role_for_user(user)


def _can_access_supervisor_dashboard(user):
    return _role_for_user(user) in {'supervisor', 'admin'}


def _attendance_source_label(attendance):
    if not attendance:
        return ''
    return ATTENDANCE_SOURCE_LABELS.get(getattr(attendance, 'recorded_by_role', ''), '')


def _attendance_conflict_message(attendance, actor_role):
    if not attendance:
        return ''

    existing_role = getattr(attendance, 'recorded_by_role', '') or ''
    if actor_role == 'admin' or existing_role not in ATTENDANCE_LOCKED_ROLES or existing_role == actor_role:
        return ''

    if existing_role == 'teacher':
        return 'تم تسجيل الحضور من قبل الأستاذ ولا يمكن تعديله من لوحة الموجه.'
    if existing_role == 'supervisor':
        return 'تم تسجيل الحضور من قبل الموجّه ولا يمكن تعديله من صفحة الأستاذ.'
    return 'تم تسجيل الحضور من قبل مستخدم آخر ولا يمكن تعديله.'


def _infer_category(grade):
    if hasattr(grade, 'category_id') and getattr(grade, 'category_id', None):
        return grade.category.name
    if hasattr(grade, 'get_category_label'):
        return grade.get_category_label()

    grade_text = (grade or '').strip()
    if 'ابتدائي' in grade_text:
        return 'المرحلة الابتدائية'
    if 'متوسط' in grade_text:
        return 'المرحلة المتوسطة'
    if 'ثانوي' in grade_text:
        return 'المرحلة الثانوية'
    return 'غير مصنف'


def _time_greeting():
    return 'السلام عليكم ورحمة الله وبركاته'


def _format_month_label(day_value):
    return day_value.strftime('%m/%Y')


def _resolve_reference_date(request):
    raw_date = request.GET.get('date', '') if request else ''
    return parse_date(raw_date) or timezone.localdate()


def _format_session_label(session):
    if not session:
        return 'لا توجد جلسة مسجلة لهذا التاريخ'
    return f'{session.start_time.strftime("%H:%M")} - {session.end_time.strftime("%H:%M")}'


def _homework_status(homework, reference_date):
    if not homework:
        return 'none'
    if homework.evaluation_date and homework.evaluation_date <= reference_date:
        return 'evaluated'
    if homework.assigned_date == reference_date:
        return 'assigned'
    return 'pending'


def _build_homework_snapshot(homework, reference_date):
    if not homework:
        return None

    status = _homework_status(homework, reference_date)
    status_labels = {
        'assigned': 'تم الإسناد',
        'pending': 'بانتظار التقييم',
        'evaluated': 'تم التقييم',
    }
    meta_text = f'{homework.get_assignment_type_display()}: {homework.assignment_text}'
    if status == 'evaluated' and homework.evaluation_date:
        detail_text = f'{homework.get_evaluation_display()} - {homework.evaluation_date.isoformat()}'
    else:
        detail_text = f'أُسند في {homework.assigned_date.isoformat()}'
        if homework.expected_recitation_date:
            detail_text = f'{detail_text}، التسميع المتوقع {homework.expected_recitation_date.isoformat()}'

    return {
        'id': homework.id,
        'status': status,
        'status_label': status_labels[status],
        'assignment_type': homework.assignment_type,
        'assignment_type_label': homework.get_assignment_type_display(),
        'assignment_text': homework.assignment_text,
        'pages': homework.pages,
        'surah': homework.surah,
        'from_verse': homework.from_verse,
        'to_verse': homework.to_verse,
        'assignment_notes': homework.assignment_notes,
        'assigned_date': homework.assigned_date,
        'assigned_date_iso': homework.assigned_date.isoformat(),
        'expected_recitation_date': homework.expected_recitation_date,
        'expected_recitation_date_iso': (
            homework.expected_recitation_date.isoformat() if homework.expected_recitation_date else ''
        ),
        'evaluation': homework.evaluation,
        'evaluation_label': homework.get_evaluation_display() if homework.evaluation else '',
        'evaluation_date': homework.evaluation_date,
        'evaluation_date_iso': homework.evaluation_date.isoformat() if homework.evaluation_date else '',
        'evaluation_notes': homework.evaluation_notes,
        'meta_text': meta_text,
        'detail_text': detail_text,
    }


def _empty_daily_history_entry(day_value):
    return {
        'date': day_value.isoformat(),
        'date_label': day_value.strftime('%Y-%m-%d'),
        'display_date': day_value.strftime('%d/%m/%Y'),
        'session_label': 'لا توجد جلسة مسجلة لهذا التاريخ',
        'present': [],
        'absent': [],
        'excused': [],
        'notes': [],
        'highlights': [],
    }


def _build_daily_history(*, halaqa, student_ids, selected_date):
    if not student_ids:
        return [_empty_daily_history_entry(selected_date)]

    history_by_date = {}

    def ensure_entry(day_value):
        if day_value not in history_by_date:
            history_by_date[day_value] = _empty_daily_history_entry(day_value)
        return history_by_date[day_value]

    sessions = list(
        Session.objects.filter(halaqa=halaqa).order_by('-date', '-start_time')
    )
    attendances = list(
        Attendance.objects.filter(
            session__halaqa=halaqa,
            student_id__in=student_ids,
        ).select_related('student', 'session').order_by('-session__date', 'student__name')
    )
    memorization_records = list(
        MemorizationRecord.objects.filter(
            student_id__in=student_ids,
        ).select_related('student').order_by('-date', 'student__name')
    )
    point_transactions = list(
        PointTransaction.objects.filter(
            student_id__in=student_ids,
            halaqa=halaqa,
        ).select_related('student').order_by('-date', 'student__name')
    )
    homeworks = list(
        Homework.objects.filter(
            student_id__in=student_ids,
            halaqa=halaqa,
        ).select_related('student').order_by('-assigned_date', 'student__name')
    )
    plans = list(
        Plan.objects.filter(
            student_id__in=student_ids,
            halaqa=halaqa,
        ).select_related('student').order_by('-start_date', 'student__name')
    )

    for session in sessions:
        entry = ensure_entry(session.date)
        entry['session_label'] = _format_session_label(session)
        if session.notes:
            entry['notes'].append(session.notes)

    for attendance in attendances:
        entry = ensure_entry(attendance.session.date)
        entry[attendance.status].append(attendance.student.name)
        if attendance.notes:
            entry['notes'].append(f'{attendance.student.name}: {attendance.notes}')

    for record in memorization_records:
        entry = ensure_entry(record.date)
        label = f'{record.student.name}: تسميع {record.recitation_title} {record.recitation_range}'.strip()
        if record.evaluation:
            label = f'{label} ({record.get_evaluation_display()})'
        entry['highlights'].append(label)

    for transaction in point_transactions:
        entry = ensure_entry(transaction.date.date())
        signed_value = f'{transaction.value:+}'
        highlight = f'{transaction.student.name}: {signed_value} نقطة'
        if transaction.reason:
            highlight = f'{highlight} - {transaction.reason}'
        entry['highlights'].append(highlight)

    for homework in homeworks:
        assign_entry = ensure_entry(homework.assigned_date)
        assign_label = (
            f'{homework.student.name}: واجب {homework.get_assignment_type_display()} - '
            f'{homework.assignment_text}'
        )
        assign_entry['highlights'].append(assign_label)
        if homework.assignment_notes:
            assign_entry['notes'].append(f'واجب {homework.student.name}: {homework.assignment_notes}')

        if homework.evaluation_date:
            evaluation_entry = ensure_entry(homework.evaluation_date)
            evaluation_label = (
                f'{homework.student.name}: تقييم واجب - {homework.get_evaluation_display()}'
            )
            evaluation_entry['highlights'].append(evaluation_label)
            if homework.evaluation_notes:
                evaluation_entry['notes'].append(f'تقييم {homework.student.name}: {homework.evaluation_notes}')

    for plan in plans:
        entry = ensure_entry(plan.start_date)
        entry['highlights'].append(f'خطة {plan.student.name}: {plan.target}')
        if plan.notes:
            entry['notes'].append(f'خطة {plan.student.name}: {plan.notes}')

    ensure_entry(selected_date)

    history = []
    for day_value in sorted(history_by_date.keys(), reverse=True):
        entry = history_by_date[day_value]
        for key in ('present', 'absent', 'excused'):
            entry[key] = list(dict.fromkeys(entry[key]))
        entry['notes'] = list(dict.fromkeys(entry['notes']))
        entry['highlights'] = list(dict.fromkeys(entry['highlights']))
        history.append(entry)
    return history


ARABIC_WEEKDAYS = {
    0: 'الاثنين',
    1: 'الثلاثاء',
    2: 'الأربعاء',
    3: 'الخميس',
    4: 'الجمعة',
    5: 'السبت',
    6: 'الأحد',
}


def _daily_report_recitation_line(record):
    title = (record.surah or record.pages or '').strip()
    content_parts = [title, (record.recitation_range or '').strip()]
    content = ' '.join(part for part in content_parts if part).strip()
    evaluation = record.get_evaluation_display() if record.evaluation else 'بدون تقييم'
    if content:
        return f'• {record.student.name} - {content} ({evaluation})'
    return f'• {record.student.name} - ({evaluation})'


def _build_daily_report(
    *,
    today,
    recitation_records,
    halaqa=None,
    teacher_name='',
    student_count=0,
    category_badges=None,
    grade_badges=None,
    current_session=None,
    today_attendance_summary=None,
    monthly_points_total=0,
    monthly_verses_total=0,
    monthly_records_count=0,
    monthly_attendance_rate=0,
):
    report_lines = [
        'تقرير اليوم:',
    ]
    report_lines.extend(_daily_report_recitation_line(record) for record in recitation_records)
    return '\n'.join(report_lines)


class TeacherStudentViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = StudentSerializer

    def get_queryset(self):
        return Student.objects.all()


class TeacherAttendanceViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = AttendanceSerializer

    def get_queryset(self):
        queryset = Attendance.objects.select_related('student', 'session__halaqa', 'recorded_by')
        student_id = self.request.query_params.get('student')
        session_id = self.request.query_params.get('session')
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        return queryset

    def create(self, request, *args, **kwargs):
        user = request.user if getattr(request.user, 'is_authenticated', False) else None
        role = _role_for_user(user)
        session_id = request.data.get('session')
        student_id = request.data.get('student')
        existing_attendance = None
        if session_id and student_id:
            existing_attendance = Attendance.objects.filter(
                session_id=session_id,
                student_id=student_id,
            ).first()
        if existing_attendance:
            conflict_message = _attendance_conflict_message(existing_attendance, role)
            if conflict_message:
                return Response({'detail': conflict_message}, status=status.HTTP_409_CONFLICT)

            serializer = self.get_serializer(existing_attendance, data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        user = request.user if getattr(request.user, 'is_authenticated', False) else None
        role = _role_for_user(user)
        conflict_message = _attendance_conflict_message(instance, role)
        if conflict_message:
            return Response({'detail': conflict_message}, status=status.HTTP_409_CONFLICT)

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def perform_create(self, serializer):
        user = self.request.user if getattr(self.request.user, 'is_authenticated', False) else None
        serializer.save(recorded_by=user, recorded_by_role=_role_for_user(user))

    def perform_update(self, serializer):
        user = self.request.user if getattr(self.request.user, 'is_authenticated', False) else None
        serializer.save(recorded_by=user, recorded_by_role=_role_for_user(user))


class TeacherPointViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = PointSerializer

    def get_queryset(self):
        queryset = PointTransaction.objects.select_related('student', 'halaqa')
        student_id = self.request.query_params.get('student')
        halaqa_id = self.request.query_params.get('halaqa')
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        if halaqa_id:
            queryset = queryset.filter(halaqa_id=halaqa_id)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user if getattr(self.request.user, 'is_authenticated', False) else None
        serializer.save(created_by=user)


class TeacherPlanViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = PlanSerializer

    def get_queryset(self):
        queryset = Plan.objects.select_related('student', 'halaqa')
        student_id = self.request.query_params.get('student')
        halaqa_id = self.request.query_params.get('halaqa')
        is_completed = self.request.query_params.get('is_completed')
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        if halaqa_id:
            queryset = queryset.filter(halaqa_id=halaqa_id)
        if is_completed in {'true', 'false'}:
            queryset = queryset.filter(is_completed=(is_completed == 'true'))
        return queryset

    def perform_create(self, serializer):
        serializer.save()


class TeacherHomeworkViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = HomeworkSerializer

    def get_queryset(self):
        queryset = Homework.objects.select_related('student', 'halaqa')
        student_id = self.request.query_params.get('student')
        halaqa_id = self.request.query_params.get('halaqa')
        pending = self.request.query_params.get('pending')
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        if halaqa_id:
            queryset = queryset.filter(halaqa_id=halaqa_id)
        if pending in {'true', 'false'}:
            queryset = queryset.filter(evaluation_date__isnull=(pending == 'true'))
        return queryset

    def perform_create(self, serializer):
        user = self.request.user if getattr(self.request.user, 'is_authenticated', False) else None
        validated_data = serializer.validated_data
        evaluated_by = user if validated_data.get('evaluation') and validated_data.get('evaluation_date') else None
        serializer.save(created_by=user, evaluated_by=evaluated_by)

    def perform_update(self, serializer):
        user = self.request.user if getattr(self.request.user, 'is_authenticated', False) else None
        evaluation = serializer.validated_data.get('evaluation', serializer.instance.evaluation)
        evaluation_date = serializer.validated_data.get('evaluation_date', serializer.instance.evaluation_date)
        if evaluation and evaluation_date:
            serializer.save(evaluated_by=user)
        else:
            serializer.save()


@login_required
def teacher_dashboard(request):
    teacher = request.user.teacher
    verses_expr = ExpressionWrapper(
        F('memorization_records__to_verse') - F('memorization_records__from_verse') + Value(1),
        output_field=IntegerField(),
    )

    students = Student.objects.filter(
        halaqa_memberships__halaqa__teachers=teacher,
        halaqa_memberships__is_active=True,
    ).annotate(
        total_points=Sum('point_transactions__value'),
        memorized_verses=Sum(verses_expr),
        present_count=Count('attendances', filter=Q(attendances__status='present')),
        absent_count=Count('attendances', filter=Q(attendances__status='absent')),
    ).select_related('parent')

    halaqas = Halaqa.objects.filter(
        teachers=teacher,
    ).annotate(
        student_count=Count('members', filter=Q(members__is_active=True)),
    )

    dashboard_data = []
    for student in students:
        current_plan = Plan.objects.filter(student=student, is_completed=False).first()
        dashboard_data.append({
            'student': student,
            'present': student.present_count,
            'absent': student.absent_count,
            'points': student.total_points or 0,
            'memorized': student.memorized_verses or 0,
            'plan': current_plan,
        })

    return render(request, 'halaqas/teacher_dashboard.html', {
        'teacher': teacher,
        'dashboard_data': dashboard_data,
        'halaqas': halaqas,
    })


@login_required
def supervisor_dashboard(request):
    if not _can_access_supervisor_dashboard(request.user):
        raise PermissionDenied("لا تملك صلاحية الوصول إلى لوحة الموجه.")

    return _supervisor_attendance_dashboard(request)


def supervisor_attendance_share(request, token):
    get_object_or_404(SupervisorAttendanceShare, token=token, is_active=True)
    return _supervisor_attendance_dashboard(request, share_token=token)


def _supervisor_attendance_dashboard(request, share_token=None):
    is_public_share = bool(share_token)
    raw_date = request.POST.get('selected_date') if request.method == 'POST' else request.GET.get('date', '')
    selected_date = parse_date(raw_date or '') or timezone.localdate()

    selection_source = request.POST if request.method == 'POST' else request.GET

    def selected_pk(name):
        raw_value = (selection_source.get(name, '') or '').strip()
        return int(raw_value) if raw_value.isdigit() else None

    selected_category_id = selected_pk('category')
    selected_halaqa_id = selected_pk('halaqa')

    categories = list(
        Category.objects.annotate(
            active_halaqa_count=Count(
                'halaqas',
                filter=Q(halaqas__is_active=True),
                distinct=True,
            ),
            active_student_count=Count(
                'halaqas__members',
                filter=Q(
                    halaqas__is_active=True,
                    halaqas__members__is_active=True,
                ),
                distinct=True,
            ),
        ).order_by('display_order', 'code')
    )
    selected_category = next(
        (category for category in categories if category.id == selected_category_id),
        None,
    )

    if selected_category is None and selected_halaqa_id:
        hinted_category_id = (
            Halaqa.objects.filter(
                pk=selected_halaqa_id,
                is_active=True,
                category_id__isnull=False,
            )
            .values_list('category_id', flat=True)
            .first()
        )
        selected_category = next(
            (category for category in categories if category.id == hinted_category_id),
            None,
        )

    active_halaqa_queryset = (
        Halaqa.objects.filter(is_active=True)
        .select_related('category')
        .prefetch_related('teachers')
        .annotate(
            active_student_count=Count(
                'members',
                filter=Q(members__is_active=True),
                distinct=True,
            )
        )
        .order_by('name')
    )
    category_halaqas = list(
        active_halaqa_queryset.filter(category=selected_category)
        if selected_category
        else []
    )
    selected_halaqa = next(
        (halaqa for halaqa in category_halaqas if halaqa.id == selected_halaqa_id),
        None,
    )

    if selected_halaqa:
        membership_filters = Q(halaqa=selected_halaqa)
    elif request.method == 'POST' and not selected_category_id and not selected_halaqa_id:
        membership_filters = Q(halaqa__is_active=True)
    else:
        membership_filters = Q(pk__isnull=True)

    active_memberships = list(
        HalaqaMembership.objects.filter(
            membership_filters,
            halaqa__is_active=True,
            is_active=True,
        )
        .select_related('halaqa', 'student', 'student__parent')
        .order_by('halaqa__name', 'student__name')
    )

    def dashboard_url(category=None, halaqa=None):
        params = {'date': selected_date.isoformat()}
        if category:
            params['category'] = category.id
        if halaqa:
            params['halaqa'] = halaqa.id
        if is_public_share:
            return f'{reverse("halaqas:supervisor_attendance_share", args=[share_token])}?{urlencode(params)}'
        return f'{reverse("halaqas:supervisor_dashboard")}?{urlencode(params)}'

    if request.method == 'POST':
        saved_count = 0
        conflict_count = 0
        role = 'supervisor' if is_public_share else _role_for_user(request.user)
        recorded_by = None if is_public_share else request.user
        sessions_by_halaqa = {}

        with transaction.atomic():
            for membership in active_memberships:
                student_id = membership.student_id
                status_value = request.POST.get(f'status_{student_id}', '')
                if status_value not in ATTENDANCE_STATUS_LABELS:
                    continue

                session = sessions_by_halaqa.get(membership.halaqa_id)
                if session is None:
                    session, _ = Session.objects.get_or_create(
                        halaqa=membership.halaqa,
                        date=selected_date,
                        defaults={
                            'start_time': time(0, 0),
                            'end_time': time(0, 0),
                        },
                    )
                    sessions_by_halaqa[membership.halaqa_id] = session

                existing_attendance = (
                    Attendance.objects.select_for_update()
                    .filter(session=session, student_id=student_id)
                    .first()
                )
                conflict_message = _attendance_conflict_message(existing_attendance, role)
                if conflict_message:
                    conflict_count += 1
                    continue

                Attendance.objects.update_or_create(
                    session=session,
                    student_id=student_id,
                    defaults={
                        'status': status_value,
                        'notes': request.POST.get(f'notes_{student_id}', '').strip(),
                        'recorded_by': recorded_by,
                        'recorded_by_role': role,
                    },
                )
                saved_count += 1

        if saved_count:
            messages.success(request, f'تم حفظ حضور {saved_count} طالب/طالبة ليوم {selected_date.isoformat()}.')
        if conflict_count:
            messages.error(request, f'لم يتم تعديل {conflict_count} سجل لأن الحضور مسجل من قبل الأستاذ.')
        if not saved_count and not conflict_count:
            messages.warning(request, 'لم يتم اختيار أي حالة حضور للحفظ.')
        return redirect(dashboard_url(selected_category, selected_halaqa))

    student_ids = [membership.student_id for membership in active_memberships]

    sessions_by_halaqa = {
        session.halaqa_id: session
        for session in Session.objects.filter(
            halaqa__in=[selected_halaqa] if selected_halaqa else [],
            date=selected_date,
        )
    }
    attendance_map = {}
    if sessions_by_halaqa and student_ids:
        for attendance in Attendance.objects.filter(
            session_id__in=[session.id for session in sessions_by_halaqa.values()],
            student_id__in=student_ids,
        ).select_related('recorded_by', 'session'):
            attendance_map[(attendance.session.halaqa_id, attendance.student_id)] = attendance

    student_rows = []
    marked_total = 0
    status_counts = {'present': 0, 'absent': 0, 'excused': 0}
    if selected_halaqa:
        for membership in active_memberships:
            attendance = attendance_map.get((selected_halaqa.id, membership.student_id))
            status_value = attendance.status if attendance else ''
            locked_for_supervisor = bool(attendance and attendance.recorded_by_role == 'teacher')
            if status_value in status_counts:
                status_counts[status_value] += 1
                marked_total += 1
            student_rows.append({
                'student': membership.student,
                'attendance': attendance,
                'status': status_value,
                'status_label': ATTENDANCE_STATUS_LABELS.get(status_value, 'غير مسجل'),
                'notes': attendance.notes if attendance else '',
                'source_label': _attendance_source_label(attendance),
                'locked_for_supervisor': locked_for_supervisor,
                'lock_message': 'تم تسجيل الحضور من قبل الأستاذ' if locked_for_supervisor else '',
            })

    category_rows = [
        {
            'category': category,
            'is_selected': bool(selected_category and category.id == selected_category.id),
            'active_halaqa_count': category.active_halaqa_count,
            'active_student_count': category.active_student_count,
            'url': dashboard_url(category=category),
        }
        for category in categories
    ]
    halaqa_options = [
        {
            'halaqa': halaqa,
            'is_selected': bool(selected_halaqa and halaqa.id == selected_halaqa.id),
            'student_count': halaqa.active_student_count,
            'teacher_names': '، '.join(teacher.full_name for teacher in halaqa.teachers.all()) or 'لا يوجد معلم',
            'url': dashboard_url(category=selected_category, halaqa=halaqa),
        }
        for halaqa in category_halaqas
    ]
    halaqa_rows = [
        {
            'halaqa': selected_halaqa,
            'students': student_rows,
            'student_count': len(student_rows),
            'marked_count': sum(status_counts.values()),
            'status_counts': status_counts,
            'session': sessions_by_halaqa.get(selected_halaqa.id),
        }
    ] if selected_halaqa else []

    return render(request, 'halaqas/supervisor_dashboard.html', {
        'selected_date': selected_date,
        'category_rows': category_rows,
        'halaqa_options': halaqa_options,
        'selected_category': selected_category,
        'selected_halaqa': selected_halaqa,
        'student_rows': student_rows,
        'status_counts': status_counts,
        'halaqa_rows': halaqa_rows,
        'status_options': [
            {'value': 'present', 'label': 'حاضر', 'icon': 'fas fa-user-check'},
            {'value': 'absent', 'label': 'غائب', 'icon': 'fas fa-user-xmark'},
            {'value': 'excused', 'label': 'غياب مبرر', 'icon': 'fas fa-circle-exclamation'},
        ],
        'is_public_share': is_public_share,
        'share_token': share_token,
        'summary': {
            'halaqa_count': Halaqa.objects.filter(is_active=True).count(),
            'student_count': HalaqaMembership.objects.filter(halaqa__is_active=True, is_active=True).count(),
            'marked_count': marked_total,
        },
    })


@login_required
def halaqa_detail(request, pk=None, join_code=None):
    lookup = {'pk': pk} if pk is not None else {'join_code': join_code}
    halaqa = get_object_or_404(
        Halaqa.objects.prefetch_related('teachers__user', 'members__student'),
        **lookup,
    )
    if not user_can_access_halaqa(request.user, halaqa):
        raise PermissionDenied("لا تملك صلاحية الوصول إلى هذه الحلقة.")
    return prepare_halaqa_view(
        request,
        halaqa,
        'halaqas/halaqa_detail.html',
        ensure_current_session=True,
    )


@require_GET
@login_required
def halaqa_share_view(request, link_code):
    halaqa = get_object_or_404(
        Halaqa.objects.prefetch_related('teachers__user', 'members__student'),
        shareable_link=link_code,
    )
    if not user_can_access_halaqa(request.user, halaqa):
        raise PermissionDenied("لا تملك صلاحية الوصول إلى هذه الحلقة.")
    return prepare_halaqa_view(request, halaqa, 'halaqas/halaqa_share.html')


def prepare_halaqa_view(request, halaqa, template_name, ensure_current_session=False):
    today = _resolve_reference_date(request)
    month_start = today.replace(day=1)
    teachers = list(halaqa.teachers.all().select_related('user'))

    current_teacher = getattr(request.user, 'teacher', None) if getattr(request, 'user', None) else None
    if current_teacher and current_teacher not in teachers:
        current_teacher = None
    display_teacher = current_teacher or (teachers[0] if teachers else None)

    students = list(
        Student.objects.filter(
            halaqa_memberships__halaqa=halaqa,
            halaqa_memberships__is_active=True,
        ).select_related('parent').prefetch_related('memorization_records').distinct().order_by('name')
    )
    student_ids = [student.id for student in students]

    points_rows = PointTransaction.objects.filter(
        student_id__in=student_ids,
        halaqa=halaqa,
        date__date__lte=today,
    ).values('student_id').annotate(total=Coalesce(Sum('value'), 0))
    points_map = {row['student_id']: row['total'] for row in points_rows}

    attendance_rows = Attendance.objects.filter(
        student_id__in=student_ids,
        session__halaqa=halaqa,
        session__date__lte=today,
    ).values('student_id').annotate(
        present=Count('id', filter=Q(status='present')),
        absent=Count('id', filter=Q(status='absent')),
        excused=Count('id', filter=Q(status='excused')),
    )
    attendance_map = {
        row['student_id']: {
            'present': row['present'],
            'absent': row['absent'],
            'excused': row['excused'],
        }
        for row in attendance_rows
    }

    memorization_rows = MemorizationRecord.objects.filter(
        student_id__in=student_ids,
        date__lte=today,
    ).values('student_id').annotate(total=Coalesce(Sum(VERSE_COUNT_EXPR), 0))
    memorization_map = {row['student_id']: row['total'] for row in memorization_rows}

    current_plans = {}
    for plan in Plan.objects.filter(
        student_id__in=student_ids,
        halaqa=halaqa,
        is_completed=False,
        start_date__lte=today,
        end_date__gte=today,
    ).order_by('student_id', '-start_date', '-id'):
        current_plans.setdefault(plan.student_id, plan)

    current_homeworks = {}
    for homework in Homework.objects.filter(
        student_id__in=student_ids,
        halaqa=halaqa,
        assigned_date__lte=today,
        evaluation_date__isnull=True,
    ).order_by('student_id', '-assigned_date', '-id'):
        current_homeworks.setdefault(homework.student_id, homework)
    for homework in Homework.objects.filter(
        student_id__in=student_ids,
        halaqa=halaqa,
        assigned_date__lte=today,
    ).exclude(student_id__in=list(current_homeworks.keys())).order_by('student_id', '-assigned_date', '-id'):
        current_homeworks.setdefault(homework.student_id, homework)

    current_session = Session.objects.filter(
        halaqa=halaqa,
        date=today,
    ).first()
    if ensure_current_session and current_session is None:
        current_session = Session.objects.create(
            halaqa=halaqa,
            date=today,
            start_time=time(0, 0),
            end_time=time(0, 0),
        )
    current_session_id = current_session.id if current_session else None

    today_attendance_map = {}
    if current_session_id:
        for attendance in Attendance.objects.filter(
            session_id=current_session_id,
            student_id__in=student_ids,
        ):
            today_attendance_map[attendance.student_id] = attendance

    month_points_total = PointTransaction.objects.filter(
        student_id__in=student_ids,
        halaqa=halaqa,
        date__date__range=(month_start, today),
    ).aggregate(total=Coalesce(Sum('value'), 0))['total']

    month_memorization_qs = MemorizationRecord.objects.filter(
        student_id__in=student_ids,
        date__range=(month_start, today),
    )
    month_verses_total = month_memorization_qs.aggregate(
        total=Coalesce(Sum(VERSE_COUNT_EXPR), 0)
    )['total']
    month_records_count = month_memorization_qs.count()
    today_recitation_records = list(
        MemorizationRecord.objects.filter(
            student_id__in=student_ids,
            date=today,
        ).select_related('student').order_by('student__name', 'id')
    )
    today_recitations_by_student = defaultdict(list)
    for record in today_recitation_records:
        today_recitations_by_student[record.student_id].append(record)

    month_attendance = Attendance.objects.filter(
        student_id__in=student_ids,
        session__halaqa=halaqa,
        session__date__range=(month_start, today),
    ).aggregate(
        present=Count('id', filter=Q(status='present')),
        absent=Count('id', filter=Q(status='absent')),
        excused=Count('id', filter=Q(status='excused')),
    )
    month_attendance_total = (
        month_attendance['present'] +
        month_attendance['absent'] +
        month_attendance['excused']
    )
    month_attendance_rate = round(
        (month_attendance['present'] / month_attendance_total) * 100
    ) if month_attendance_total else 0

    today_attendance_summary = {
        'present': sum(1 for item in today_attendance_map.values() if item.status == 'present'),
        'absent': sum(1 for item in today_attendance_map.values() if item.status == 'absent'),
        'excused': sum(1 for item in today_attendance_map.values() if item.status == 'excused'),
    }

    grade_counter = Counter()
    category_counter = Counter()
    dashboard_data = []
    for student in students:
        attendance_summary = attendance_map.get(student.id, {'present': 0, 'absent': 0, 'excused': 0})
        current_plan = current_plans.get(student.id)
        current_homework = current_homeworks.get(student.id)
        homework_snapshot = _build_homework_snapshot(current_homework, today)
        today_attendance = today_attendance_map.get(student.id)
        attendance_locked_for_teacher = bool(today_attendance and today_attendance.recorded_by_role == 'supervisor')
        memorization_records = sorted(
            [record for record in student.memorization_records.all() if record.date <= today],
            key=lambda record: (record.date, record.id),
            reverse=True,
        )
        last_memorization = memorization_records[0] if memorization_records else None
        grade_label = (student.grade or '').strip()
        if grade_label:
            grade_counter[grade_label] += 1
        category_counter[_infer_category(student)] += 1

        dashboard_data.append({
            'student': student,
            'present': attendance_summary['present'],
            'absent': attendance_summary['absent'],
            'excused': attendance_summary['excused'],
            'points': points_map.get(student.id, 0),
            'memorized': memorization_map.get(student.id, 0),
            'plan': current_plan,
            'plan_id': current_plan.id if current_plan else None,
            'homework': homework_snapshot,
            'current_session_id': current_session_id,
            'today_attendance_id': today_attendance.id if today_attendance else None,
            'today_attendance_status': today_attendance.status if today_attendance else '',
            'today_attendance_notes': today_attendance.notes if today_attendance else '',
            'today_attendance_recorded_by_role': today_attendance.recorded_by_role if today_attendance else '',
            'today_attendance_source_label': _attendance_source_label(today_attendance),
            'attendance_locked_for_teacher': attendance_locked_for_teacher,
            'attendance_lock_message': 'تم تسجيل الحضور من قبل الموجّه' if attendance_locked_for_teacher else '',
            'last_memorization': last_memorization,
            'grade_label': grade_label or 'غير محدد',
            'category_label': _infer_category(student),
        })

    grade_badges = [
        {'label': label, 'count': count}
        for label, count in grade_counter.most_common()
    ]
    category_badges = [
        {'label': label, 'count': count}
        for label, count in category_counter.most_common()
    ]
    grades_text = '، '.join(item['label'] for item in grade_badges) or 'غير محدد'
    categories_text = '، '.join(item['label'] for item in category_badges) or 'غير مصنف'

    top_students = sorted(
        dashboard_data,
        key=lambda item: (-item['points'], item['student'].name),
    )[:5]
    top_students_chart = {
        'labels': [entry['student'].name for entry in top_students],
        'values': [entry['points'] for entry in top_students],
    }
    if not top_students_chart['labels']:
        top_students_chart = {'labels': ['لا يوجد طلاب'], 'values': [0]}

    attendance_chart = {
        'labels': ['حضور', 'غياب', 'مبرر'],
        'values': [
            month_attendance['present'],
            month_attendance['absent'],
            month_attendance['excused'],
        ],
    }

    memorization_chart_rows = list(
        month_memorization_qs.values('date').annotate(
            total=Coalesce(Sum(VERSE_COUNT_EXPR), 0)
        ).order_by('date')
    )
    memorization_entries = [
        {
            'date': row['date'].isoformat(),
            'label': row['date'].strftime('%d/%m'),
            'value': row['total'],
        }
        for row in memorization_chart_rows
    ]
    if not memorization_entries:
        memorization_entries = [{
            'date': today.isoformat(),
            'label': today.strftime('%d/%m'),
            'value': 0,
        }]
    memorization_chart = {
        'entries': memorization_entries,
        'labels': [entry['label'] for entry in memorization_entries],
        'values': [entry['value'] for entry in memorization_entries],
    }

    month_label = _format_month_label(today)
    teacher_name = display_teacher.full_name if display_teacher else 'غير محدد'
    current_session_label = (
        f'{current_session.start_time.strftime("%H:%M")} - {current_session.end_time.strftime("%H:%M")}'
        if current_session else 'لا توجد جلسة مسجلة لليوم'
    )
    summary_cards = [
        {
            'icon': 'fas fa-users',
            'value': len(students),
            'label': 'عدد الطلاب',
            'meta': 'الطلاب النشطون في الحلقة',
        },
        {
            'icon': 'fas fa-star',
            'value': f'{month_points_total:+}',
            'label': f'نقاط {month_label}',
            'meta': 'إجمالي الإضافات والخصومات هذا الشهر',
        },
        {
            'icon': 'fas fa-book-open',
            'value': month_verses_total,
            'label': 'آيات محفوظة هذا الشهر',
            'meta': f'{month_records_count} تسميعات مسجلة',
        },
        {
            'icon': 'fas fa-calendar-check',
            'value': f'{month_attendance_rate}%',
            'label': 'حضور الشهر',
            'meta': (
                f'{month_attendance["present"]} حاضر / {month_attendance_total} إجمالي حالات'
                if month_attendance_total else 'لا توجد سجلات حضور لهذا الشهر'
            ),
        },
    ]

    daily_history = _build_daily_history(
        halaqa=halaqa,
        student_ids=student_ids,
        selected_date=today,
    )

    daily_report_preview = _build_daily_report(
        today=today,
        recitation_records=today_recitation_records,
        halaqa=halaqa,
        teacher_name=teacher_name,
        student_count=len(students),
        category_badges=category_badges,
        grade_badges=grade_badges,
        current_session=current_session,
        today_attendance_summary=today_attendance_summary,
        monthly_points_total=month_points_total,
        monthly_verses_total=month_verses_total,
        monthly_records_count=month_records_count,
        monthly_attendance_rate=month_attendance_rate,
    )

    student_table_state = []
    for entry in dashboard_data:
        last_memorization = entry['last_memorization']
        today_recitations = today_recitations_by_student.get(entry['student'].id, [])
        today_recitation = today_recitations[-1] if today_recitations else None
        homework = entry['homework']
        student_table_state.append({
            'id': entry['student'].id,
            'name': entry['student'].name,
            'points': entry['points'],
            'present': entry['present'],
            'absent': entry['absent'],
            'excused': entry['excused'],
            'today_attendance_status': entry['today_attendance_status'],
            'today_attendance_id': entry['today_attendance_id'],
            'today_attendance_notes': entry['today_attendance_notes'],
            'today_attendance_recorded_by_role': entry['today_attendance_recorded_by_role'],
            'attendance_locked_for_teacher': entry['attendance_locked_for_teacher'],
            'plan_id': entry['plan_id'],
            'plan_target': entry['plan'].target if entry['plan'] else '',
            'plan_total_pages': entry['plan'].total_pages if entry['plan'] else '',
            'plan_start': entry['plan'].start_date.isoformat() if entry['plan'] else '',
            'plan_end': entry['plan'].end_date.isoformat() if entry['plan'] else '',
            'plan_notes': entry['plan'].notes if entry['plan'] else '',
            'homework_id': homework['id'] if homework else '',
            'homework_status': homework['status'] if homework else 'none',
            'homework_status_label': homework['status_label'] if homework else '',
            'homework_assignment_type': homework['assignment_type'] if homework else '',
            'homework_assignment_type_label': homework['assignment_type_label'] if homework else '',
            'homework_assignment_text': homework['assignment_text'] if homework else '',
            'homework_pages': homework['pages'] if homework else '',
            'homework_surah': homework['surah'] if homework else '',
            'homework_from_verse': homework['from_verse'] if homework else '',
            'homework_to_verse': homework['to_verse'] if homework else '',
            'homework_assignment_notes': homework['assignment_notes'] if homework else '',
            'homework_assigned_date': homework['assigned_date_iso'] if homework else '',
            'homework_expected_recitation_date': homework['expected_recitation_date_iso'] if homework else '',
            'homework_evaluation': homework['evaluation'] if homework else '',
            'homework_evaluation_label': homework['evaluation_label'] if homework else '',
            'homework_evaluation_date': homework['evaluation_date_iso'] if homework else '',
            'homework_evaluation_notes': homework['evaluation_notes'] if homework else '',
            'today_recitation': (
                {
                    'surah': today_recitation.surah,
                    'pages': today_recitation.pages,
                    'from_verse': today_recitation.from_verse,
                    'to_verse': today_recitation.to_verse,
                    'recitation_title': today_recitation.recitation_title,
                    'recitation_range': today_recitation.recitation_range,
                    'recitation_type': today_recitation.recitation_type,
                    'evaluation': today_recitation.evaluation,
                    'evaluation_label': today_recitation.get_evaluation_display() if today_recitation.evaluation else '',
                    'date': today_recitation.date.isoformat(),
                }
                if today_recitation else None
            ),
            'today_recitations': [
                {
                    'surah': record.surah,
                    'pages': record.pages,
                    'from_verse': record.from_verse,
                    'to_verse': record.to_verse,
                    'recitation_title': record.recitation_title,
                    'recitation_range': record.recitation_range,
                    'recitation_type': record.recitation_type,
                    'evaluation': record.evaluation,
                    'evaluation_label': record.get_evaluation_display() if record.evaluation else '',
                    'date': record.date.isoformat(),
                }
                for record in today_recitations
            ],
            'last_memorization': (
                {
                    'surah': last_memorization.surah,
                    'pages': last_memorization.pages,
                    'from_verse': last_memorization.from_verse,
                    'to_verse': last_memorization.to_verse,
                    'recitation_title': last_memorization.recitation_title,
                    'recitation_range': last_memorization.recitation_range,
                    'recitation_type': last_memorization.recitation_type,
                    'evaluation': last_memorization.evaluation,
                    'evaluation_label': last_memorization.get_evaluation_display() if last_memorization.evaluation else '',
                    'date': last_memorization.date.isoformat(),
                }
                if last_memorization else None
            ),
        })

    report_state = {
        'halaqa_name': halaqa.name,
        'teacher_name': teacher_name,
        'selected_date': today.isoformat(),
        'selected_date_display': today.strftime('%d/%m/%Y'),
        'date_label': today.strftime('%Y-%m-%d'),
        'day_name': ARABIC_WEEKDAYS.get(today.weekday(), today.strftime('%Y-%m-%d')),
        'session_label': current_session_label,
        'student_count': len(students),
        'categories_text': categories_text,
        'grades_text': grades_text,
        'month_label': month_label,
        'monthly_points_total': month_points_total,
        'monthly_verses_total': month_verses_total,
        'monthly_records_count': month_records_count,
        'monthly_attendance_rate': month_attendance_rate,
        'monthly_attendance': {
            'present': month_attendance['present'],
            'absent': month_attendance['absent'],
            'excused': month_attendance['excused'],
            'total': month_attendance_total,
        },
        'today_attendance_summary': today_attendance_summary,
        'today_chart_label': today.strftime('%d/%m'),
        'today_chart_date': today.isoformat(),
        'daily_history': daily_history,
    }

    return render(request, template_name, {
        'halaqa': halaqa,
        'dashboard_data': dashboard_data,
        'display_teacher': display_teacher,
        'teacher_greeting': _time_greeting(),
        'teacher_names': [teacher.full_name for teacher in teachers],
        'summary_cards': summary_cards,
        'grade_badges': grade_badges,
        'category_badges': category_badges,
        'today_label': today,
        'selected_date': today,
        'month_label': month_label,
        'current_session': current_session,
        'top_students_chart': top_students_chart,
        'attendance_chart': attendance_chart,
        'memorization_chart': memorization_chart,
        'daily_report_preview': daily_report_preview,
        'report_state': report_state,
        'student_table_state': student_table_state,
        'today_attendance_summary': today_attendance_summary,
        'evaluation_options': [
            {'value': value, 'label': label}
            for value, label in MemorizationRecord.EVALUATION_CHOICES
        ],
        'homework_type_options': [
            {'value': value, 'label': label}
            for value, label in Homework.ASSIGNMENT_TYPE_CHOICES
        ],
        'homework_evaluation_options': [
            {'value': value, 'label': label}
            for value, label in Homework.EVALUATION_CHOICES
        ],
        'point_reason_presets': POINT_REASON_PRESETS,
        'attendance_note_presets': ATTENDANCE_NOTE_PRESETS,
        'plan_target_presets': PLAN_TARGET_PRESETS,
    })


@login_required
def halaqa_edit(request, pk):
    halaqa = get_object_or_404(Halaqa, pk=pk)
    if request.method == 'POST':
        form = HalaqaForm(request.POST, instance=halaqa)
        if form.is_valid():
            form.save()
            return redirect('halaqas:halaqa_detail', pk=pk)
    else:
        form = HalaqaForm(instance=halaqa)
    return render(request, 'halaqas/halaqa_form.html', {'form': form, 'halaqa': halaqa})


@login_required
def add_student_to_halaqa(request, pk):
    halaqa = get_object_or_404(Halaqa, pk=pk)
    return render(request, 'halaqas/add_student_to_halaqa.html', {'halaqa': halaqa})


@api_view(['GET'])
def halaqa_students_api(request, link_code):
    halaqa = get_object_or_404(Halaqa, shareable_link=link_code)
    students = Student.objects.filter(
        halaqa_memberships__halaqa=halaqa,
        halaqa_memberships__is_active=True,
    ).annotate(
        total_points=Sum('point_transactions__value'),
        attendance_rate=ExpressionWrapper(
            Count('attendances', filter=Q(attendances__status='present')) * 100.0 /
            Count('attendances'),
            output_field=FloatField(),
        ),
    ).values(
        'id',
        'name',
        'grade',
        'total_points',
        'attendance_rate',
    )
    return Response(list(students), status=status.HTTP_200_OK)


def halaqa_students_list(request, halaqa_id):
    halaqa = get_object_or_404(Halaqa, id=halaqa_id)
    return prepare_halaqa_view(request, halaqa, 'halaqas/students_list.html')
