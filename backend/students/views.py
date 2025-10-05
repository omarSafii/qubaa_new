from rest_framework import viewsets, mixins, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404, render
from django.db.models import Sum, Q, Count ,ExpressionWrapper,F,Value,IntegerField
from datetime import date
from .models import Student,MemorizationRecord
from .serializers import StudentRegistrationSerializer, StudentSerializer, MemorizationRecordSerializer
from halaqas.models import *
class StudentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet):
    queryset = Student.objects.all()
    lookup_field = 'access_token'
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        if self.action == 'create':
            return StudentRegistrationSerializer
        return StudentSerializer

        
        
        
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student = serializer.save()
        
        # إنشاء الرابط الكامل باستخدام request
        full_access_url = request.build_absolute_uri(f'/students/{student.access_token}/')
        
        return Response({
            "msg": "تم تسجيل الطالب بنجاح",
            "student_id": student.id,
            "access_token": str(student.access_token),
            "access_link": full_access_url  # الآن يحتوي على الرابط الكامل
        }, status=status.HTTP_201_CREATED)
        
        

    
    
    def retrieve(self, request, *args, **kwargs):
        # 1) جلب الطالب بناءً على التوكن
        token = kwargs['access_token']
        student = get_object_or_404(Student, access_token=token)

        # 2) إيجاد عضوية الحلقة الفعّالة لهذا الطالب
        membership = HalaqaMembership.objects.filter(
            student=student, is_active=True
        ).select_related('halaqa').first()
        halaqa = membership.halaqa if membership else None

        # 3) تهيئة QuerySets للنقاط والحضور بناءً على وجود عضوية
        if halaqa:
            points_qs = PointTransaction.objects.filter(student=student, halaqa=halaqa)
            attendance_qs = Attendance.objects.filter(student=student, session__halaqa=halaqa)
        else:
            points_qs = PointTransaction.objects.filter(student=student)
            attendance_qs = Attendance.objects.filter(student=student)

        # 4) حساب إجمالي النقاط
        total_points = points_qs.aggregate(sum=Sum('value'))['sum'] or 0

        # 5) حساب الحضور والغياب
        present_count = attendance_qs.filter(status='present').count()
        absent_count  = attendance_qs.filter(status='absent').count()
        total_sessions = present_count + absent_count
        attendance_percentage = (
            round((present_count / total_sessions) * 100, 1)
            if total_sessions > 0 else 0
        )

        # 6) حساب إجمالي الآيات المحفوظة
        verses_expr = ExpressionWrapper(
            F('to_verse') - F('from_verse') + Value(1),
            output_field=IntegerField()
        )
        memorized = student.memorization_records.aggregate(
            total=Sum(verses_expr)
        )['total'] or 0
        memorized_parts = round(memorized / 20, 1)

        # 7) جلب الخطة الحالية غير المكتملة
        current_plan = Plan.objects.filter(
            student=student,
            halaqa=halaqa,
            is_completed=False
        ).first()

        # 8) الحصول على الجلسة الحالية (أو إنشاؤها)
        current_session = None
        if halaqa:
            current_session, _ = Session.objects.get_or_create(
                halaqa=halaqa,
                date=date.today(),
                defaults={'start_time': '00:00', 'end_time': '00:00'}
            )

        # 9) عرض القالب مع كل المتغيرات
        return render(request, 'students/students_data.html', {
            'student':                student,
            'parent_name':            student.parent.first_name if student.parent else '',
            'parent_phone':           student.parent_phone,
            'halaqa':                 halaqa,
            'total_points':           total_points,
            'present_count':          present_count,
            'absent_count':           absent_count,
            'attendance_percentage':  attendance_percentage,
            'memorized':              memorized,
            'memorized_parts':        memorized_parts,
            'current_plan':           current_plan,
            'current_session':        current_session,
        })

    
    

    @action(detail=False, methods=['get'], url_path='dashboard', permission_classes=[AllowAny])
    def dashboard(self, request):
        # جلب جميع الحلقات الفعّالة مع عدد الأعضاء النشطين فيها
        halaqas = Halaqa.objects.filter(is_active=True).annotate(
            member_count=Count('members', filter=Q(members__is_active=True))
        )
        # تمرير الحلقات إلى القالب (الصفحة التي عندك باسم dashboard تُستخدم كصفحة التسجيل)
        return render(request, 'students/dashboard.html', {
            'halaqas': halaqas
        })
    
    
    
    
class MemorizationRecordViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet):
        queryset = MemorizationRecord.objects.all()
        serializer_class = MemorizationRecordSerializer
        permission_classes = [AllowAny]
        lookup_field = 'id'  # أو استخدم الافتراضي pk

        def get_queryset(self):
            """
            لو حابب تحدد إظهار السجلات بناء على الطالب أو الحلقة.
            مثلاً إذا عندك مستخدم مرتبط بحلقة تريد إظهار سجلات طلاب الحلقة فقط.
                حالياً ترجع كل السجلات.
            """
            # مثال: استرجاع سجلات حفظ لطالب معين من باراميتر
            student_id = self.request.query_params.get('student_id')
            if student_id:
                return self.queryset.filter(student__id=student_id)
            return self.queryset.all()

        def create(self, request, *args, **kwargs):
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            memorization_record = serializer.save()
            return Response({
              "msg": "تم إنشاء سجل الحفظ بنجاح",
              "record_id": memorization_record.id
               }, status=status.HTTP_201_CREATED)
            
            
            
            
            
            
            
            
 