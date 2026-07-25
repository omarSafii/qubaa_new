import re
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
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

    def seed_memorization_days(self, count):
        today = timezone.localdate()
        for offset in range(count):
            MemorizationRecord.objects.create(
                student=self.student,
                halaqa=self.halaqa,
                pages=f'صفحة {offset + 1}',
                date=today - timedelta(days=offset),
            )
        return today

    def test_students_data_route_uses_existing_retrieve_view_without_creating_session(self):
        response = self.client.get(reverse('students:students_data', args=[self.student.access_token]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Session.objects.count(), 0)

    def test_attendance_is_historical_per_session_and_unique_per_student_session(self):
        first_session = Session.objects.create(
            halaqa=self.halaqa,
            date=timezone.localdate() - timedelta(days=2),
            start_time=time(16, 0),
            end_time=time(18, 0),
        )
        second_session = Session.objects.create(
            halaqa=self.halaqa,
            date=timezone.localdate() - timedelta(days=1),
            start_time=time(16, 0),
            end_time=time(18, 0),
        )

        Attendance.objects.create(session=first_session, student=self.student, status='present')
        Attendance.objects.create(session=second_session, student=self.student, status='absent')

        self.assertEqual(Attendance.objects.filter(student=self.student).count(), 2)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Attendance.objects.create(session=first_session, student=self.student, status='excused')

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
            recorded_by=self.teacher_user,
            recorded_by_role='teacher',
            notes='حضر مبكراً',
        )
        today_session = Session.objects.create(
            halaqa=self.halaqa,
            date=today,
            start_time=time(16, 0),
            end_time=time(18, 0),
            notes='جلسة اليوم',
        )
        Attendance.objects.create(
            session=today_session,
            student=self.student,
            status='excused',
            recorded_by=self.teacher_user,
            recorded_by_role='teacher',
            notes='عذر مقبول',
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
        self.assertEqual(response.context['master_report']['attendance']['excused'], 1)
        self.assertEqual(response.context['master_report']['attendance']['total'], 2)
        self.assertEqual(response.context['master_report']['attendance']['percentage'], 50)
        self.assertEqual(len(response.context['attendance_rows']), 2)
        self.assertEqual(len(response.context['timeline_entries']), 2)
        self.assertContains(response, 'ملخص الطالب')
        self.assertContains(response, 'عرض سجل الحضور')
        self.assertContains(response, 'سورة الملك')
        self.assertContains(response, 'أستاذ الحلقة')

    def test_plan_progress_uses_total_pages_when_available(self):
        today = timezone.localdate()
        Plan.objects.create(
            student=self.student,
            halaqa=self.halaqa,
            start_date=today - timedelta(days=5),
            end_date=today + timedelta(days=15),
            target='خطة صفحات',
            total_pages=60,
        )
        MemorizationRecord.objects.create(
            student=self.student,
            halaqa=self.halaqa,
            recitation_type='extra',
            pages='1-15',
            date=today - timedelta(days=1),
            evaluation='very_good',
            is_approved=True,
        )

        response = self.client.get(reverse('students:students_data', args=[self.student.access_token]))

        plan = response.context['summary']['plan']
        self.assertEqual(plan['total_pages'], 60)
        self.assertEqual(plan['completed_pages'], 15)
        self.assertEqual(plan['remaining_pages'], 45)
        self.assertEqual(plan['actual_percent'], 25)
        self.assertEqual(plan['required_pages_per_day'], 3)
        self.assertContains(response, 'عدد صفحات الخطة')
        self.assertContains(response, '45 صفحة')

    def test_extra_recitation_page_reference_displays_raw_text(self):
        today = timezone.localdate()
        MemorizationRecord.objects.create(
            student=self.student,
            halaqa=self.halaqa,
            recitation_type='extra',
            pages='صفحة 8',
            date=today,
            evaluation='excellent',
            is_approved=True,
        )

        response = self.client.get(reverse('students:students_data', args=[self.student.access_token]))

        self.assertEqual(response.context['summary']['latest_recitation']['surah'], 'صفحة 8')
        self.assertContains(response, 'صفحة 8')
        self.assertNotContains(response, 'صفحات صفحة 8')

    def test_parent_page_header_uses_real_student_name(self):
        response = self.client.get(reverse('students:students_data', args=[self.student.access_token]))

        self.assertContains(response, 'السلام عليكم ورحمة الله وبركاته')
        self.assertContains(response, f'صفحة ولي أمر الطالب: {self.student.name}')
        self.assertNotContains(response, str(self.student.access_token))

    def test_latest_recitation_and_next_homework_are_real_records(self):
        today = timezone.localdate()
        MemorizationRecord.objects.create(
            student=self.student,
            halaqa=self.halaqa,
            surah='النبأ',
            from_verse=1,
            to_verse=12,
            date=today,
            evaluation='excellent',
            notes='قراءة متقنة',
        )
        Homework.objects.create(
            student=self.student,
            halaqa=self.halaqa,
            assigned_date=today,
            assignment_type='pages',
            assignment_text='الصفحات 20-22',
            pages='20-22',
            expected_recitation_date=today + timedelta(days=3),
            assignment_notes='مراجعة هادئة',
        )

        response = self.client.get(reverse('students:students_data', args=[self.student.access_token]))

        self.assertContains(response, 'سورة النبأ')
        self.assertContains(response, 'قراءة متقنة')
        self.assertContains(response, 'الصفحات 20-22')
        self.assertContains(response, 'مراجعة هادئة')

    def test_empty_parent_page_has_friendly_states(self):
        response = self.client.get(reverse('students:students_data', args=[self.student.access_token]))

        self.assertContains(response, 'لم يُسجل تسميع بعد')
        self.assertContains(response, 'لم يُحدد التسميع القادم بعد')
        self.assertContains(response, 'لا توجد سجلات للطالب ضمن الفترة المحددة')

    def test_parent_page_defaults_to_memorization_tab_and_90_day_period(self):
        response = self.client.get(reverse('students:students_data', args=[self.student.access_token]))

        dashboard = response.context['parent_dashboard']
        self.assertEqual(dashboard['active_tab'], 'memorization')
        self.assertEqual(dashboard['period'], '90')
        self.assertContains(response, 'value="90" selected')
        self.assertNotContains(response, 'name="start_date"')
        self.assertNotContains(response, 'name="end_date"')
        self.assertNotContains(response, '>تطبيق<', html=True)
        self.assertNotContains(response, '>مسح الفلتر<', html=True)

    def test_period_options_30_90_180_and_all_work(self):
        self.seed_memorization_days(200)
        url = reverse('students:students_data', args=[self.student.access_token])

        recent_30 = self.client.get(url, {'period': '30'})
        recent_90 = self.client.get(url, {'period': '90'})
        recent_180 = self.client.get(url, {'period': '180'})
        all_days = self.client.get(url, {'period': 'all'})

        self.assertEqual(recent_30.context['parent_dashboard']['total_days'], 30)
        self.assertEqual(recent_90.context['parent_dashboard']['total_days'], 90)
        self.assertEqual(recent_180.context['parent_dashboard']['total_days'], 180)
        self.assertEqual(all_days.context['parent_dashboard']['total_days'], 200)
        self.assertEqual(len(all_days.context['parent_dashboard']['rows']), 10)
        self.assertGreater(all_days.context['parent_dashboard']['page_obj'].paginator.num_pages, 1)

    def test_invalid_tab_and_period_fall_back_to_defaults(self):
        response = self.client.get(
            reverse('students:students_data', args=[self.student.access_token]),
            {'tab': 'unknown', 'period': '999'},
        )

        dashboard = response.context['parent_dashboard']
        self.assertEqual(dashboard['active_tab'], 'memorization')
        self.assertEqual(dashboard['period'], '90')

    def test_charts_render_inside_charts_tab_only(self):
        response = self.client.get(reverse('students:students_data', args=[self.student.access_token]))
        html = response.content.decode()
        before_charts, marker, charts_panel = html.partition('data-panel="charts"')

        self.assertTrue(marker)
        self.assertNotIn('سير الخطة', before_charts)
        self.assertNotIn('تقدم الطالب في الحفظ', before_charts)
        self.assertNotIn('الأداء العام', before_charts)
        self.assertIn('سير الخطة', charts_panel)
        self.assertIn('تقدم الطالب في الحفظ', charts_panel)
        self.assertIn('الأداء العام', charts_panel)

    def test_charts_tab_hides_pagination_and_uses_charts_active_state(self):
        self.seed_memorization_days(12)
        response = self.client.get(
            reverse('students:students_data', args=[self.student.access_token]),
            {'tab': 'charts', 'period': 'all', 'page': 2},
        )

        self.assertEqual(response.context['parent_dashboard']['active_tab'], 'charts')
        self.assertContains(response, 'data-pagination-wrap hidden')
        self.assertContains(response, 'data-panel="charts"')

    def test_unified_days_are_identical_and_multiple_points_share_one_row(self):
        today = timezone.localdate()
        session = Session.objects.create(
            halaqa=self.halaqa,
            date=today,
            start_time=time(16, 0),
            end_time=time(18, 0),
        )
        Attendance.objects.create(session=session, student=self.student, status='present')
        for value in (3, 4):
            PointTransaction.objects.create(
                student=self.student,
                halaqa=self.halaqa,
                value=value,
                reason='نشاط',
                date=timezone.make_aware(datetime.combine(today, time(12, value))),
            )

        response = self.client.get(reverse('students:students_data', args=[self.student.access_token]))
        rows = response.context['parent_dashboard']['rows']

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['date'], today)
        self.assertEqual(len(rows[0]['points']), 2)
        self.assertEqual(rows[0]['points_total'], 7)
        self.assertGreaterEqual(response.content.decode().count(today.isoformat()), 5)

    def test_absence_and_missing_attendance_have_distinct_messages(self):
        today = timezone.localdate()
        absent_day = today - timedelta(days=1)
        session = Session.objects.create(
            halaqa=self.halaqa,
            date=absent_day,
            start_time=time(16, 0),
            end_time=time(18, 0),
        )
        Attendance.objects.create(session=session, student=self.student, status='absent')
        PointTransaction.objects.create(
            student=self.student,
            halaqa=self.halaqa,
            value=0,
            reason='قيمة فعلية صفر',
            date=timezone.make_aware(datetime.combine(today, time(12, 0))),
        )

        response = self.client.get(reverse('students:students_data', args=[self.student.access_token]))

        self.assertContains(response, 'الطالب غائب، لذلك لا توجد بيانات لهذا اليوم')
        self.assertContains(response, 'لم تُسجل حالة الحضور لهذا اليوم')
        self.assertContains(response, 'المجموع: 0')

    def test_present_day_without_points_has_clear_message(self):
        today = timezone.localdate()
        session = Session.objects.create(
            halaqa=self.halaqa,
            date=today,
            start_time=time(16, 0),
            end_time=time(18, 0),
        )
        Attendance.objects.create(session=session, student=self.student, status='present')

        response = self.client.get(reverse('students:students_data', args=[self.student.access_token]))

        self.assertContains(response, 'لم تُسجل نقاط لهذا اليوم')

    def test_date_filter_and_pagination_preserve_tab(self):
        today = timezone.localdate()
        for offset in range(12):
            MemorizationRecord.objects.create(
                student=self.student,
                halaqa=self.halaqa,
                pages=f'صفحة {offset + 1}',
                date=today - timedelta(days=offset),
            )

        response = self.client.get(
            reverse('students:students_data', args=[self.student.access_token]),
            {'period': 'all', 'page': 2, 'tab': 'points'},
        )

        dashboard = response.context['parent_dashboard']
        self.assertEqual(dashboard['page_obj'].number, 2)
        self.assertEqual(len(dashboard['rows']), 2)
        self.assertEqual(dashboard['active_tab'], 'points')
        self.assertEqual(dashboard['period'], 'all')
        self.assertIn('tab=points', dashboard['filter_query'])
        self.assertIn('period=all', dashboard['filter_query'])

        filtered = self.client.get(
            reverse('students:students_data', args=[self.student.access_token]),
            {
                'start_date': (today - timedelta(days=2)).isoformat(),
                'end_date': today.isoformat(),
            },
        )
        self.assertEqual(len(filtered.context['parent_dashboard']['rows']), 3)

    def test_period_change_preserves_current_tab_state(self):
        self.seed_memorization_days(40)
        response = self.client.get(
            reverse('students:students_data', args=[self.student.access_token]),
            {'tab': 'attendance', 'period': '30'},
        )

        dashboard = response.context['parent_dashboard']
        self.assertEqual(dashboard['active_tab'], 'attendance')
        self.assertEqual(dashboard['period'], '30')
        self.assertContains(response, 'id="activeTabInput" value="attendance"')
        self.assertContains(response, 'value="30" selected')

    def test_table_tabs_share_same_unified_days_and_row_count(self):
        self.seed_memorization_days(14)
        url = reverse('students:students_data', args=[self.student.access_token])

        memorization_response = self.client.get(url, {'period': 'all', 'page': 2, 'tab': 'memorization'})
        attendance_response = self.client.get(url, {'period': 'all', 'page': 2, 'tab': 'attendance'})
        points_response = self.client.get(url, {'period': 'all', 'page': 2, 'tab': 'points'})

        memorization_rows = memorization_response.context['parent_dashboard']['rows']
        attendance_rows = attendance_response.context['parent_dashboard']['rows']
        points_rows = points_response.context['parent_dashboard']['rows']

        self.assertEqual([row['date'] for row in memorization_rows], [row['date'] for row in attendance_rows])
        self.assertEqual([row['date'] for row in memorization_rows], [row['date'] for row in points_rows])
        self.assertEqual(len(memorization_rows), len(attendance_rows))
        self.assertEqual(len(memorization_rows), len(points_rows))

    def test_parent_page_includes_sticky_tabs_and_mobile_layout_rules(self):
        response = self.client.get(reverse('students:students_data', args=[self.student.access_token]))
        html = response.content.decode()

        self.assertIn('position: sticky;', html)
        self.assertIn('overflow-x: auto;', html)
        self.assertIn('@media (max-width: 600px)', html)
        self.assertRegex(html, re.compile(r'data-tab="charts"', re.S))

    def test_parent_token_never_leaks_another_students_records(self):
        other_parent = User.objects.create_user(username='other_parent_dashboard', password='StrongPass123!')
        other_student = Student.objects.create(
            name='طالب آخر',
            birth_date='2013-01-01',
            parent=other_parent,
        )
        HalaqaMembership.objects.create(student=other_student, halaqa=self.halaqa, is_active=True)
        MemorizationRecord.objects.create(
            student=other_student,
            halaqa=self.halaqa,
            pages='بيانات الطالب الآخر',
            date=timezone.localdate(),
        )

        response = self.client.get(reverse('students:students_data', args=[self.student.access_token]))

        self.assertNotContains(response, 'بيانات الطالب الآخر')
        self.assertNotContains(response, other_student.name)

    def test_query_count_does_not_scale_per_daily_record(self):
        url = reverse('students:students_data', args=[self.student.access_token])
        with CaptureQueriesContext(connection) as initial_queries:
            self.client.get(url)

        today = timezone.localdate()
        for offset in range(8):
            MemorizationRecord.objects.create(
                student=self.student,
                halaqa=self.halaqa,
                pages=f'صفحة {offset}',
                date=today - timedelta(days=offset),
            )
        with CaptureQueriesContext(connection) as populated_queries:
            self.client.get(url)

        self.assertLess(len(populated_queries) - len(initial_queries), 8)
