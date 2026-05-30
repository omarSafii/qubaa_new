from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from halaqas.models import (
    Attendance,
    Category,
    Halaqa,
    HalaqaMembership,
    Homework,
    Plan,
    PointTransaction,
    Session,
    Teacher,
)
from .models import MemorizationRecord, Student


User = get_user_model()


class StudentRegistrationTests(TestCase):
    def test_student_registration_returns_real_parent_dashboard_link(self):
        halaqa = Halaqa.objects.create(name='Registration Halaqa')

        response = self.client.post('/students/', data={
            'name': 'Student One',
            'birth_date': '2015-01-01',
            'halaqa_id': halaqa.id,
            'parent_name': 'Parent One',
            'parent_phone': '0999000',
            'address': 'Damascus',
            'grade': '5',
        })

        self.assertEqual(response.status_code, 201)

        parent = User.objects.get(username='parent_0999000')
        student = Student.objects.get(parent=parent)
        self.assertTrue(parent.has_usable_password())
        self.assertTrue(
            response.json()['access_link'].endswith(
                reverse('students:students_data', args=[student.access_token])
            )
        )


class StudentCategoryModelTests(TestCase):
    def test_student_save_infers_official_category_from_grade(self):
        Category.seed_official_categories()
        parent = User.objects.create_user(username='student_category_parent', password='StrongPass123!')

        student = Student.objects.create(
            name='طالب التصنيف',
            birth_date='2010-01-01',
            parent=parent,
            parent_phone='0999444444',
            grade='الصف التاسع',
        )

        self.assertIsNotNone(student.category_id)
        self.assertEqual(student.category.code, '5')


class StudentReadOnlyViewTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            username='parent_user',
            password='StrongPass123!',
            first_name='ولي الأمر',
        )
        self.teacher_user = User.objects.create_user(
            username='teacher_user',
            password='StrongPass123!',
        )
        self.teacher = Teacher.objects.create(
            user=self.teacher_user,
            full_name='أستاذ الحلقة',
            phone='09995555',
        )
        self.halaqa = Halaqa.objects.create(name='Student Data Halaqa')
        self.halaqa.teachers.add(self.teacher)
        self.student = Student.objects.create(
            name='Student Two',
            birth_date='2014-02-02',
            parent=self.parent,
            parent_phone='0888000',
            grade='ابتدائي خامس',
        )
        HalaqaMembership.objects.create(student=self.student, halaqa=self.halaqa, is_active=True)

    def test_students_data_route_uses_existing_retrieve_view_without_creating_session(self):
        response = self.client.get(reverse('students:students_data', args=[self.student.access_token]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Session.objects.count(), 0)

    def test_parent_dashboard_context_uses_teacher_entered_data_and_range_filters(self):
        today = timezone.localdate()
        report_day = today - timedelta(days=1)

        session = Session.objects.create(
            halaqa=self.halaqa,
            date=report_day,
            start_time=time(16, 0),
            end_time=time(18, 0),
            notes='ملاحظة من الجلسة',
        )
        Attendance.objects.create(
            session=session,
            student=self.student,
            status='present',
            notes='حضر مبكراً',
        )
        PointTransaction.objects.create(
            student=self.student,
            halaqa=self.halaqa,
            value=8,
            reason='مشاركة مميزة',
            created_by=self.teacher_user,
            date=timezone.make_aware(
                datetime.combine(report_day, time(12, 0)),
                timezone.get_current_timezone(),
            ),
        )
        MemorizationRecord.objects.create(
            student=self.student,
            halaqa=self.halaqa,
            recitation_type='extra',
            surah='الملك',
            from_verse=1,
            to_verse=10,
            date=report_day,
            evaluation='excellent',
            is_approved=True,
        )
        Homework.objects.create(
            student=self.student,
            halaqa=self.halaqa,
            assigned_date=report_day,
            expected_recitation_date=today,
            assignment_type='surah',
            assignment_text='سورة الملك',
            surah='الملك',
            from_verse=1,
            to_verse=10,
            assignment_notes='مراجعة مع الإتقان',
            evaluation_date=today,
            evaluation='completed',
            evaluation_notes='تم الإنجاز',
            created_by=self.teacher_user,
            evaluated_by=self.teacher_user,
        )
        Plan.objects.create(
            student=self.student,
            halaqa=self.halaqa,
            start_date=report_day,
            end_date=today + timedelta(days=5),
            target='مراجعة المحفوظ الحالي',
            notes='خطة الأسبوع',
        )

        response = self.client.get(
            reverse('students:students_data', args=[self.student.access_token]),
            {'range': 'custom', 'start_date': report_day.isoformat(), 'end_date': today.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['summary']['teacher'], self.teacher.full_name)
        self.assertEqual(response.context['summary']['homework']['status'], 'evaluated')
        self.assertEqual(response.context['summary']['homework']['expected_recitation_date'], today.isoformat())
        self.assertEqual(response.context['summary']['latest_recitation']['source'], 'تسميع إضافي')
        self.assertEqual(response.context['master_report']['points']['net_total'], 8)
        self.assertEqual(response.context['master_report']['attendance']['present'], 1)
        self.assertEqual(len(response.context['timeline_entries']), 2)
        self.assertContains(response, 'التقرير الزمني الرئيسي')
        self.assertContains(response, 'سورة الملك')
        self.assertContains(response, 'أستاذ الحلقة')
