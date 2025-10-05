# students/admin.py
from django.contrib import admin
from .models import Student,MemorizationRecord

admin.site.register(Student)
admin.site.register(MemorizationRecord)
