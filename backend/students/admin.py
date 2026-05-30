# students/admin.py
from django.contrib import admin
from .models import Student, MemorizationRecord

admin.site.register(Student)


@admin.register(MemorizationRecord)
class MemorizationRecordAdmin(admin.ModelAdmin):
    list_display = ['student', 'halaqa', 'recitation_type', 'date', 'evaluation', 'is_approved']
    list_filter = ['halaqa', 'recitation_type', 'date', 'evaluation', 'is_approved']
    search_fields = ['student__name', 'surah', 'pages', 'notes']
    raw_id_fields = ['student', 'halaqa', 'homework']
