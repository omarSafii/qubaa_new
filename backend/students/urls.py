# students/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StudentViewSet, MemorizationRecordViewSet
app_name = 'students'

router = DefaultRouter()
router.register(r'memorization-records', MemorizationRecordViewSet, basename='memorizationrecord')
router.register(r'', StudentViewSet, basename='student')


urlpatterns = [
    # مسار لإنشاء طالب جديد مباشرة على /students/
    path('', StudentViewSet.as_view({'post': 'create'}), name='student-create'),

    # لوحة التحكم العامة
    path('dashboard/', StudentViewSet.as_view({'get': 'dashboard'}), name='dashboard'),

    # (اختياري) مسار عرض بيانات الطالب بشكل منفصل إذا كنت تستخدم action detail=True
    path('students_data/<uuid:access_token>/', 
         StudentViewSet.as_view({'get': 'retrieve'}), 
         name='students_data'),

    # المسارات الخاصة بالـ router
    path('', include(router.urls)),
]
