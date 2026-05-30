from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .admin_dashboard import master_admin_dashboard, master_admin_dashboard_export
from .views import (
    TeacherStudentViewSet,
    TeacherAttendanceViewSet,
    TeacherHomeworkViewSet,
    TeacherPointViewSet,
    TeacherPlanViewSet,
    teacher_dashboard,
    supervisor_dashboard,
    halaqa_detail,
    halaqa_share_view,
    halaqa_edit,
    add_student_to_halaqa,
    halaqa_students_api,
)

app_name = 'halaqas'

# إنشاء راوتر وحيد لواجهات الAPI تحت /halaqas/api/
router = DefaultRouter()
router.register(r'students',   TeacherStudentViewSet,    basename='students')
router.register(r'attendance', TeacherAttendanceViewSet, basename='attendance')
router.register(r'homeworks',  TeacherHomeworkViewSet,   basename='homeworks')
router.register(r'points',     TeacherPointViewSet,      basename='points')
router.register(r'plans',      TeacherPlanViewSet,       basename='plans')

urlpatterns = [
    # واجهات HTML التقليدية
    path('admin-dashboard/',            master_admin_dashboard,   name='master_admin_dashboard'),
    path('admin-dashboard/export/',     master_admin_dashboard_export, name='master_admin_dashboard_export'),
    path('supervisor/',                 supervisor_dashboard,     name='supervisor_dashboard'),
    path('dashboard/',                  teacher_dashboard,        name='teacher_dashboard'),
    path('halaqa/<int:pk>/',            halaqa_detail,            name='halaqa_detail'),
    path('halaqa/by-code/<str:join_code>/', halaqa_detail,       name='halaqa_by_code'),
    path('halaqa/<int:pk>/edit/',       halaqa_edit,              name='halaqa_edit'),
    path('halaqa/<int:pk>/add-student/', add_student_to_halaqa,   name='add_student_to_halaqa'),
    path('halaqa/share/<str:link_code>/', halaqa_share_view,      name='halaqa_share'),


    path('api/halaqas/<str:link_code>/students/', halaqa_students_api, name='halaqa-students-api'),
    
    # واجهات API تحت /api/
    path('api/', include((router.urls, app_name), namespace='api')),
    
    
]
