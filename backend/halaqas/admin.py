from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse, NoReverseMatch
from .models import Teacher, Halaqa, Session, HalaqaMembership, Attendance, PointTransaction, Plan

class HalaqaMembershipInline(admin.TabularInline):
    model = HalaqaMembership
    extra = 0
    raw_id_fields = ['student']

class SessionInline(admin.TabularInline):
    model = Session
    extra = 0

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'phone', 'qualification', 'join_date']
    search_fields = ['full_name', 'phone']
    list_filter = ['join_date']

@admin.register(Halaqa)
class HalaqaAdmin(admin.ModelAdmin):
    list_display = ['name', 'display_teachers', 'join_code', 'view_link']
    search_fields = ['name', 'join_code']
    list_filter = ['teachers']
    inlines = [HalaqaMembershipInline, SessionInline]
    
    def display_teachers(self, obj):
        return ", ".join([t.full_name for t in obj.teachers.all()])
    display_teachers.short_description = 'المعلمون'
    
    def view_link(self, obj):
        try:
            url = reverse('halaqas:halaqa_detail', kwargs={'pk': obj.pk})
            return format_html('<a href="{}" target="_blank">🔗 عرض الحلقة</a>', url)
        except NoReverseMatch:
            return "رابط غير متاح"
    view_link.short_description = 'رابط مباشر'

    def get_queryset(self, request):
        # تحسين الأداء بتقليل الاستعلامات
        return super().get_queryset(request).prefetch_related('teachers')

@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ['halaqa', 'date', 'start_time', 'end_time']
    list_filter = ['halaqa', 'date']
    date_hierarchy = 'date'
    raw_id_fields = ['halaqa']

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['student', 'session', 'status']
    list_filter = ['status', 'session__halaqa']
    search_fields = ['student__name']
    raw_id_fields = ['student', 'session']

@admin.register(PointTransaction)
class PointTransactionAdmin(admin.ModelAdmin):
    list_display = ['student', 'halaqa', 'value', 'date', 'created_by']
    list_filter = ['halaqa', 'date']
    search_fields = ['student__name']
    raw_id_fields = ['student', 'halaqa']

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ['student', 'halaqa', 'start_date', 'end_date', 'is_completed']
    list_filter = ['halaqa', 'is_completed']
    search_fields = ['student__name']
    raw_id_fields = ['student', 'halaqa']