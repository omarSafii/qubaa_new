from django.shortcuts import render, get_object_or_404
from django.db.models import F, Value, IntegerField, ExpressionWrapper
from django.db.models import Sum, Q, Count
from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import render
from django.db.models import FloatField
# في أعلى الملف views.py
from datetime import date
from rest_framework.response import Response
from rest_framework.permissions import AllowAny  # <--- استبدال IsAuthenticated بـ AllowAny
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from students.models import Student, MemorizationRecord
from students.serializers import StudentSerializer
from rest_framework.exceptions import PermissionDenied
from .forms import HalaqaForm
from django.shortcuts import redirect
from .models import (
    Halaqa,
    Attendance,
    PointTransaction,
    Plan,
    HalaqaMembership,
    Teacher,
    Session
)
from .serializers import (
    AttendanceSerializer,
    PointTransactionSerializer as PointSerializer,
    PlanSerializer,
    HalaqaSerializer
)

# ────────────────────────────────────────────────────────────────
# ViewSets للواجهات البرمجية (API)
# ────────────────────────────────────────────────────────────────

class TeacherStudentViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = StudentSerializer

    def get_queryset(self):
        return Student.objects.all()


class TeacherAttendanceViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = AttendanceSerializer

    def get_queryset(self):
        return Attendance.objects.select_related('student', 'session__halaqa')

    def perform_create(self, serializer):
        serializer.save()


class TeacherPointViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = PointSerializer

    def get_queryset(self):
        return PointTransaction.objects.select_related('student', 'halaqa')

    def perform_create(self, serializer):
        serializer.save()


class TeacherPlanViewSet(viewsets.ModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = PlanSerializer

    def get_queryset(self):
        return Plan.objects.select_related('student', 'halaqa')

    def perform_create(self, serializer):
        serializer.save()

#─────
# الواجهات التقليدية (Templates)
# ────────────────────────────────────────────────────────────────
@login_required
def teacher_dashboard(request):
    teacher = request.user.teacher_profile

    verses_expr = ExpressionWrapper(
        F('memorization_records__to_verse')
        - F('memorization_records__from_verse')
        + Value(1),
        output_field=IntegerField()
    )

    students = Student.objects.filter(
        halaqa_memberships__halaqa__teachers=teacher,
        halaqa_memberships__is_active=True
    ).annotate(
        total_points=Sum('point_transactions__value'),
        memorized_verses=Sum(verses_expr),
        present_count=Count('attendances', filter=Q(attendances__status='present')),
        absent_count=Count('attendances', filter=Q(attendances__status='absent'))
    ).select_related('parent')

    halaqas = Halaqa.objects.filter(
        teachers=teacher
    ).annotate(
        student_count=Count('members', filter=Q(members__is_active=True))
    )

    dashboard_data = []
    for student in students:
        current_plan = Plan.objects.filter(
            student=student,
            is_completed=False
        ).first()

        dashboard_data.append({
            'student':   student,
            'present':   student.present_count,
            'absent':    student.absent_count,
            'points':    student.total_points or 0,
            'memorized': student.memorized_verses or 0,
            'plan':      current_plan,
        })

    return render(request, 'halaqas/teacher_dashboard.html', {
        'teacher':      teacher,
        'dashboard_data': dashboard_data,
        'halaqas':      halaqas,
    })


@login_required
def halaqa_detail(request, pk):
    halaqa = get_object_or_404(
        Halaqa.objects.prefetch_related('teachers__user', 'members__student'),
        pk=pk
    )
    return prepare_halaqa_view(request, halaqa, 'halaqas/halaqa_detail.html')


@require_GET
def halaqa_share_view(request, link_code):
    halaqa = get_object_or_404(
        Halaqa.objects.prefetch_related('teachers__user', 'members__student'),
        shareable_link=link_code
    )
    return prepare_halaqa_view(request, halaqa, 'halaqas/halaqa_share.html')


def prepare_halaqa_view(request, halaqa, template_name):
    """دالة مساعدة لإعداد بيانات الحلقة مع تضمين معرف الجلسة الحالية."""
    from .models import Session  # للتأكد من استيراد الجلسة

    # التعبير لحساب عدد الآيات لكل سجل حفظ
    verses_expr = ExpressionWrapper(
        F('memorization_records__to_verse') - F('memorization_records__from_verse') + Value(1),
        output_field=IntegerField()
    )

    # الاستعلام الرئيسي لجلب الطلاب وإحصائياتهم
    students = Student.objects.filter(
        halaqa_memberships__halaqa=halaqa,
        halaqa_memberships__is_active=True
    ).annotate(
        total_points=Sum(
            'point_transactions__value',
            filter=Q(point_transactions__halaqa=halaqa)
        ),
        memorized_verses=Sum(verses_expr),
        present_count=Count(
            'attendances',
            filter=Q(attendances__session__halaqa=halaqa, attendances__status='present')
        ),
        absent_count=Count(
            'attendances',
            filter=Q(attendances__session__halaqa=halaqa, attendances__status='absent')
        )
    ).select_related('parent')

    # الحصول على أحدث جلسة (حسب التاريخ) للحلقة
    current_session, _ = Session.objects.get_or_create(
    halaqa=halaqa,
    date=date.today(),
    defaults={'start_time': '00:00', 'end_time': '00:00'}
)
    session_id = current_session.id
    dashboard_data = []
    for student in students:
        current_plan = Plan.objects.filter(
            student=student,
            halaqa=halaqa,
            is_completed=False
        ).first()

        dashboard_data.append({
            'student':             student,
            'present':             student.present_count,
            'absent':              student.absent_count,
            'points':              student.total_points or 0,
            'memorized':           student.memorized_verses or 0,
            'plan':                current_plan,
            'current_session_id':  session_id,      # إضافة معرف الجلسة
        })

    return render(request, template_name, {
        'halaqa':        halaqa,
        'dashboard_data': dashboard_data,
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
        halaqa_memberships__is_active=True
    ).annotate(
        total_points=Sum('point_transactions__value'),
        attendance_rate=ExpressionWrapper(
            Count('attendances', filter=Q(attendances__status='present')) * 100.0 / 
            Count('attendances'),
            output_field=FloatField()
        )
    ).values(
        'id', 
        'full_name',
        'last_memorized_surah',
        'total_points',
        'attendance_rate'
    )
    
    return Response(list(students))



def halaqa_students_list(request, halaqa_id):
    """
    عرض قائمة طلاب الحلقة مع روابط ملفاتهم الشخصية
    """
    halaqa = get_object_or_404(Halaqa, id=halaqa_id)
    
    # استخدام الدالة prepare_halaqa_view الموجودة لديك مع تعديلات
    response = prepare_halaqa_view(request, halaqa, 'halaqas/students_list.html')
    
    # إضافة الروابط للطلاب
    if hasattr(response, 'context_data'):
        dashboard_data = response.context_data.get('dashboard_data', [])
        
        for student_data in dashboard_data:
            student = student_data['student']
            student_data['access_link'] = student.get_access_link(request)
    
    return response