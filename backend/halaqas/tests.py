import json
from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from students.models import MemorizationRecord, Student
from .models import Attendance, Category, Halaqa, HalaqaMembership, Homework, Plan, PointTransaction, Session, Teacher, TeacherAssignment


User = get_user_model()


class HalaqaShareViewTests(TestCase):
    def test_share_view_resolves_under_halaqas_prefix_without_creating_session(self):
        parent = User.objects.create_user(username='share_parent', password='StrongPass123!')
        halaqa = Halaqa.objects.create(name='Shared Halaqa')
        student = Student.objects.create(
            name='Shared Student',
            birth_date='2013-03-03',
            parent=parent,
            parent_phone='0777000',
        )
        HalaqaMembership.objects.create(student=student, halaqa=halaqa, is_active=True)

        response = self.client.get(f'/halaqas/halaqa/share/{halaqa.shareable_link}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Session.objects.count(), 0)


class InstituteStructureSyncTests(TestCase):
    def test_active_membership_backfills_halaqa_and_student_category(self):
        Category.seed_official_categories()
        parent = User.objects.create_user(username='category_parent', password='StrongPass123!')
        halaqa = Halaqa.objects.create(name='حلقة الصفوف الوسطى')
        student = Student.objects.create(
            name='طالب الفئة',
            birth_date='2013-03-03',
            parent=parent,
            parent_phone='0777111111',
            grade='ابتدائي خامس',
        )

        HalaqaMembership.objects.create(student=student, halaqa=halaqa, is_active=True)

        student.refresh_from_db()
        halaqa.refresh_from_db()

        self.assertEqual(student.halaqa_id, halaqa.id)
        self.assertIsNotNone(student.category_id)
        self.assertEqual(student.category_id, halaqa.category_id)
        self.assertEqual(student.category.code, '2')

    def test_teacher_transfer_keeps_one_current_halaqa_and_assignment_history(self):
        user = User.objects.create_user(username='transfer_teacher', password='StrongPass123!')
        teacher = Teacher.objects.create(
            user=user,
            full_name='معلم النقل',
            phone='0999222222',
        )
        first_halaqa = Halaqa.objects.create(name='الحلقة الأولى')
        second_halaqa = Halaqa.objects.create(name='الحلقة الثانية')

        first_halaqa.teachers.add(teacher)
        teacher.refresh_from_db()
        self.assertEqual(teacher.current_halaqa_id, first_halaqa.id)
        self.assertTrue(
            TeacherAssignment.objects.filter(teacher=teacher, halaqa=first_halaqa, is_active=True).exists()
        )

        second_halaqa.teachers.add(teacher)
        teacher.refresh_from_db()

        self.assertEqual(teacher.current_halaqa_id, second_halaqa.id)
        self.assertEqual(set(teacher.halaqas.values_list('id', flat=True)), {second_halaqa.id})
        self.assertEqual(TeacherAssignment.objects.filter(teacher=teacher, is_active=True).count(), 1)
        self.assertTrue(
            TeacherAssignment.objects.filter(teacher=teacher, halaqa=first_halaqa, is_active=False).exists()
        )
        self.assertTrue(
            TeacherAssignment.objects.filter(teacher=teacher, halaqa=second_halaqa, is_active=True).exists()
        )


class HalaqaDetailPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='teacher_user', password='StrongPass123!')
        self.teacher = Teacher.objects.create(
            user=self.user,
            full_name='محمد أحمد',
            phone='0999999999',
        )
        self.parent = User.objects.create_user(username='parent_user', password='StrongPass123!')
        self.halaqa = Halaqa.objects.create(name='الحلقة السابعة')
        self.halaqa.teachers.add(self.teacher)

        self.student = Student.objects.create(
            name='أحمد خالد',
            birth_date='2013-04-16',
            parent=self.parent,
            parent_phone='0555555555',
            grade='ابتدائي خامس',
        )
        HalaqaMembership.objects.create(student=self.student, halaqa=self.halaqa, is_active=True)

        self.session = Session.objects.create(
            halaqa=self.halaqa,
            date=timezone.localdate(),
            start_time=time(16, 0),
            end_time=time(18, 0),
        )
        Attendance.objects.create(
            session=self.session,
            student=self.student,
            status='present',
            notes='حضر في الوقت',
        )
        PointTransaction.objects.create(
            student=self.student,
            halaqa=self.halaqa,
            value=10,
            reason='مشاركة مميزة',
        )
        Plan.objects.create(
            student=self.student,
            halaqa=self.halaqa,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=7),
            target='مراجعة المحفوظ الحالي',
        )
        MemorizationRecord.objects.create(
            student=self.student,
            surah='البقرة',
            from_verse=1,
            to_verse=5,
            evaluation='excellent',
            is_approved=True,
        )
        Homework.objects.create(
            student=self.student,
            halaqa=self.halaqa,
            assigned_date=timezone.localdate(),
            assignment_type='surah',
            assignment_text='سورة الملك',
        )

    def test_detail_page_renders_incremental_dashboard_features(self):
        self.client.force_login(self.user)

        response = self.client.get(f'/halaqas/halaqa/{self.halaqa.pk}/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'نسخ التقرير')
        self.assertContains(response, self.teacher.full_name)
        self.assertContains(response, self.student.grade)
        self.assertContains(response, 'ممتاز')
        self.assertContains(response, 'عدد الطلاب')
        self.assertContains(response, 'الحضور')
        self.assertContains(response, 'معاينة التقرير اليومي')
        self.assertContains(response, 'سورة الملك')
        self.assertNotContains(response, 'بطاقة الحلقة')
        self.assertNotContains(response, 'إضافة طالب')
        self.assertNotContains(response, 'تعديل الحلقة')
        self.assertEqual(response.context['summary_cards'][0]['value'], 1)
        self.assertEqual(response.context['dashboard_data'][0]['today_attendance_status'], 'present')
        self.assertEqual(response.context['dashboard_data'][0]['homework']['status'], 'assigned')

    def test_detail_page_creates_current_session_when_missing(self):
        Session.objects.filter(pk=self.session.pk).delete()
        self.client.force_login(self.user)

        response = self.client.get(reverse('halaqas:halaqa_detail', args=[self.halaqa.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Session.objects.filter(
                halaqa=self.halaqa,
                date=timezone.localdate(),
            ).exists()
        )

    def test_detail_page_uses_requested_date_context_for_daily_data(self):
        selected_date = timezone.localdate() - timedelta(days=1)
        selected_session = Session.objects.create(
            halaqa=self.halaqa,
            date=selected_date,
            start_time=time(15, 30),
            end_time=time(17, 0),
        )
        Attendance.objects.create(
            session=selected_session,
            student=self.student,
            status='absent',
            notes='غاب في هذا اليوم',
        )
        PointTransaction.objects.create(
            student=self.student,
            halaqa=self.halaqa,
            value=7,
            reason='تفاعل يومي',
            date=timezone.make_aware(
                timezone.datetime.combine(selected_date, time(12, 0)),
                timezone.get_current_timezone(),
            ),
        )
        MemorizationRecord.objects.create(
            student=self.student,
            surah='آل عمران',
            from_verse=1,
            to_verse=4,
            evaluation='good',
            date=selected_date,
            is_approved=True,
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse('halaqas:halaqa_detail', args=[self.halaqa.pk]),
            {'date': selected_date.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['report_state']['selected_date'], selected_date.isoformat())
        self.assertEqual(response.context['report_state']['today_attendance_summary']['absent'], 1)
        self.assertEqual(response.context['dashboard_data'][0]['today_attendance_status'], 'absent')
        self.assertEqual(response.context['dashboard_data'][0]['points'], 7)
        self.assertEqual(response.context['memorization_chart']['entries'][-1]['date'], selected_date.isoformat())


class SupervisorDashboardTests(TestCase):
    def setUp(self):
        self.supervisor = User.objects.create_user(username='supervisor_user', password='StrongPass123!')
        self.supervisor.profile.role = 'supervisor'
        self.supervisor.profile.save(update_fields=['role'])

        self.admin_user = User.objects.create_user(username='role_admin_user', password='StrongPass123!')
        self.admin_user.profile.role = 'admin'
        self.admin_user.profile.save(update_fields=['role'])

        self.teacher_user = User.objects.create_user(username='supervisor_teacher_user', password='StrongPass123!')
        self.teacher_user.profile.role = 'teacher'
        self.teacher_user.profile.save(update_fields=['role'])
        self.teacher = Teacher.objects.create(
            user=self.teacher_user,
            full_name='معلم الحلقة',
            phone='0999000111',
        )

        self.parent = User.objects.create_user(username='supervisor_parent', password='StrongPass123!')
        self.category = Category.objects.create(
            code='A',
            name='فئة إشرافية',
            grade_span='اختبار',
            display_order=1,
        )
        self.halaqa = Halaqa.objects.create(name='حلقة إشرافية', category=self.category)
        self.halaqa.teachers.add(self.teacher)
        self.student = Student.objects.create(
            name='طالب الموجه',
            birth_date='2014-01-01',
            parent=self.parent,
            parent_phone='0555000111',
            grade='ابتدائي رابع',
        )
        HalaqaMembership.objects.create(student=self.student, halaqa=self.halaqa, is_active=True)

    def test_supervisor_dashboard_allows_supervisors_and_admins_only(self):
        url = reverse('halaqas:supervisor_dashboard')

        self.client.force_login(self.supervisor)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'لوحة الموجه')

        self.client.force_login(self.admin_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        self.client.force_login(self.teacher_user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_supervisor_records_attendance_visible_to_teacher_and_parent(self):
        selected_date = timezone.localdate()
        self.client.force_login(self.supervisor)

        response = self.client.post(reverse('halaqas:supervisor_dashboard'), {
            'selected_date': selected_date.isoformat(),
            'category': str(self.category.id),
            'halaqa': str(self.halaqa.id),
            f'status_{self.student.id}': 'excused',
            f'notes_{self.student.id}': 'عذر مقبول من ولي الأمر',
        })

        self.assertRedirects(
            response,
            (
                f'{reverse("halaqas:supervisor_dashboard")}?date={selected_date.isoformat()}'
                f'&category={self.category.id}&halaqa={self.halaqa.id}'
            ),
        )
        attendance = Attendance.objects.get(student=self.student, session__halaqa=self.halaqa)
        self.assertEqual(attendance.status, 'excused')
        self.assertEqual(attendance.notes, 'عذر مقبول من ولي الأمر')
        self.assertEqual(attendance.recorded_by, self.supervisor)
        self.assertEqual(attendance.recorded_by_role, 'supervisor')

        self.client.force_login(self.teacher_user)
        teacher_response = self.client.get(
            reverse('halaqas:halaqa_detail', args=[self.halaqa.pk]),
            {'date': selected_date.isoformat()},
        )
        self.assertEqual(teacher_response.status_code, 200)
        self.assertEqual(teacher_response.context['dashboard_data'][0]['today_attendance_status'], 'excused')
        self.assertEqual(teacher_response.context['dashboard_data'][0]['today_attendance_source_label'], 'المصدر: الموجه')
        self.assertContains(teacher_response, 'عذر مقبول من ولي الأمر')
        self.assertContains(teacher_response, 'المصدر: الموجه')
        self.assertContains(teacher_response, 'تم تسجيل الحضور من قبل الموجّه')
        self.assertContains(teacher_response, 'attendance-locked')

        parent_response = self.client.get(reverse('students:students_data', args=[self.student.access_token]))
        self.assertEqual(parent_response.status_code, 200)
        self.assertEqual(parent_response.context['summary']['attendance_reference']['status_code'], 'excused')
        self.assertEqual(parent_response.context['summary']['attendance_reference']['source_label'], 'المصدر: الموجه')
        self.assertContains(parent_response, 'عذر مقبول من ولي الأمر')
        self.assertContains(parent_response, 'المصدر')
        self.assertContains(parent_response, 'موجه')

    def test_supervisor_cannot_overwrite_teacher_attendance(self):
        selected_date = timezone.localdate()
        session = Session.objects.create(
            halaqa=self.halaqa,
            date=selected_date,
            start_time=time(15, 0),
            end_time=time(17, 0),
        )
        attendance = Attendance.objects.create(
            session=session,
            student=self.student,
            status='present',
            notes='تسجيل الأستاذ',
            recorded_by=self.teacher_user,
            recorded_by_role='teacher',
        )

        self.client.force_login(self.supervisor)
        response = self.client.post(
            reverse('halaqas:supervisor_dashboard'),
            {
                'selected_date': selected_date.isoformat(),
                'category': str(self.category.id),
                'halaqa': str(self.halaqa.id),
                f'status_{self.student.id}': 'absent',
                f'notes_{self.student.id}': 'محاولة تعديل',
            },
            follow=True,
        )

        attendance.refresh_from_db()
        self.assertEqual(attendance.status, 'present')
        self.assertEqual(attendance.notes, 'تسجيل الأستاذ')
        self.assertContains(response, 'تم تسجيل الحضور من قبل الأستاذ')
        self.assertContains(response, 'is-locked')

    def test_supervisor_dashboard_filters_halaqas_and_students_by_selection(self):
        other_parent = User.objects.create_user(username='other_supervisor_parent', password='StrongPass123!')
        other_category = Category.objects.create(
            code='B',
            name='فئة أخرى',
            grade_span='اختبار',
            display_order=2,
        )
        other_halaqa = Halaqa.objects.create(name='حلقة أخرى', category=other_category)
        other_student = Student.objects.create(
            name='طالب آخر',
            birth_date='2014-02-02',
            parent=other_parent,
            parent_phone='0555000222',
            grade='ابتدائي خامس',
        )
        HalaqaMembership.objects.create(student=other_student, halaqa=other_halaqa, is_active=True)

        self.client.force_login(self.supervisor)
        category_response = self.client.get(
            reverse('halaqas:supervisor_dashboard'),
            {
                'date': timezone.localdate().isoformat(),
                'category': str(self.category.id),
            },
        )

        self.assertEqual(category_response.status_code, 200)
        self.assertEqual(category_response.context['selected_category'], self.category)
        self.assertEqual([row['halaqa'] for row in category_response.context['halaqa_options']], [self.halaqa])
        self.assertContains(category_response, self.halaqa.name)
        self.assertNotContains(category_response, other_halaqa.name)
        self.assertEqual(category_response.context['student_rows'], [])

        halaqa_response = self.client.get(
            reverse('halaqas:supervisor_dashboard'),
            {
                'date': timezone.localdate().isoformat(),
                'category': str(self.category.id),
                'halaqa': str(self.halaqa.id),
            },
        )

        self.assertEqual(halaqa_response.status_code, 200)
        self.assertEqual(halaqa_response.context['selected_halaqa'], self.halaqa)
        self.assertEqual([row['student'] for row in halaqa_response.context['student_rows']], [self.student])
        self.assertContains(halaqa_response, self.student.name)
        self.assertNotContains(halaqa_response, other_student.name)

    def test_teacher_api_cannot_overwrite_supervisor_attendance(self):
        selected_date = timezone.localdate()
        session = Session.objects.create(
            halaqa=self.halaqa,
            date=selected_date,
            start_time=time(15, 0),
            end_time=time(17, 0),
        )
        attendance = Attendance.objects.create(
            session=session,
            student=self.student,
            status='excused',
            notes='تسجيل الموجه',
            recorded_by=self.supervisor,
            recorded_by_role='supervisor',
        )

        self.client.force_login(self.teacher_user)
        patch_response = self.client.patch(
            reverse('halaqas:api:attendance-detail', args=[attendance.id]),
            data=json.dumps({
                'student': self.student.id,
                'session': session.id,
                'status': 'present',
                'notes': 'محاولة تعديل',
            }),
            content_type='application/json',
        )
        post_response = self.client.post(reverse('halaqas:api:attendance-list'), data={
            'student': self.student.id,
            'session': session.id,
            'status': 'absent',
            'notes': 'محاولة إنشاء مكررة',
        })

        attendance.refresh_from_db()
        self.assertEqual(patch_response.status_code, 409)
        self.assertEqual(post_response.status_code, 409)
        self.assertIn('الموجّه', patch_response.json()['detail'])
        self.assertEqual(attendance.status, 'excused')
        self.assertEqual(attendance.notes, 'تسجيل الموجه')


class HalaqaActionEndpointTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username='api_parent', password='StrongPass123!')
        self.halaqa = Halaqa.objects.create(name='حلقة الإجراءات')
        self.student = Student.objects.create(
            name='طالب الإجراءات',
            birth_date='2012-05-05',
            parent=self.parent,
            parent_phone='0666666666',
            grade='ابتدائي سادس',
        )
        HalaqaMembership.objects.create(student=self.student, halaqa=self.halaqa, is_active=True)
        self.session = Session.objects.create(
            halaqa=self.halaqa,
            date=timezone.localdate(),
            start_time=time(15, 0),
            end_time=time(17, 0),
        )

    def test_create_endpoints_used_by_halaqa_detail_page(self):
        memorization_response = self.client.post(reverse('students:memorizationrecord-list'), data={
            'student': self.student.id,
            'halaqa': self.halaqa.id,
            'recitation_type': 'extra',
            'surah': 'البقرة',
            'from_verse': 1,
            'to_verse': 3,
            'evaluation': 'good',
            'notes': 'تسميع إضافي',
            'is_approved': True,
        })
        attendance_response = self.client.post(reverse('halaqas:api:attendance-list'), data={
            'student': self.student.id,
            'session': self.session.id,
            'status': 'present',
            'notes': 'حضر في الوقت',
        })
        plan_response = self.client.post(reverse('halaqas:api:plans-list'), data={
            'student': self.student.id,
            'halaqa': self.halaqa.id,
            'start_date': timezone.localdate(),
            'end_date': timezone.localdate() + timedelta(days=7),
            'target': 'مراجعة المحفوظ الحالي',
            'total_pages': 40,
            'notes': 'جاهز للبداية',
        })

        self.assertEqual(memorization_response.status_code, 201)
        self.assertEqual(attendance_response.status_code, 201)
        self.assertEqual(plan_response.status_code, 201)
        self.assertEqual(MemorizationRecord.objects.filter(student=self.student).count(), 1)
        memorization_record = MemorizationRecord.objects.get(student=self.student)
        self.assertEqual(memorization_record.halaqa, self.halaqa)
        self.assertEqual(memorization_record.recitation_type, 'extra')
        self.assertIsNone(memorization_record.homework)
        self.assertEqual(memorization_record.notes, 'تسميع إضافي')
        self.assertEqual(Attendance.objects.filter(student=self.student, session=self.session).count(), 1)
        self.assertEqual(Plan.objects.filter(student=self.student, halaqa=self.halaqa).count(), 1)
        self.assertEqual(Plan.objects.get(student=self.student, halaqa=self.halaqa).total_pages, 40)

    def test_update_endpoints_used_by_halaqa_detail_page(self):
        attendance = Attendance.objects.create(
            session=self.session,
            student=self.student,
            status='absent',
            notes='غاب',
        )
        plan = Plan.objects.create(
            student=self.student,
            halaqa=self.halaqa,
            start_date=timezone.localdate(),
            end_date=timezone.localdate() + timedelta(days=5),
            target='خطة أولى',
            notes='ملاحظة قديمة',
        )

        attendance_response = self.client.patch(
            reverse('halaqas:api:attendance-detail', args=[attendance.id]),
            data=json.dumps({
                'student': self.student.id,
                'session': self.session.id,
                'status': 'excused',
                'notes': 'بعذر',
            }),
            content_type='application/json',
        )
        plan_response = self.client.patch(
            reverse('halaqas:api:plans-detail', args=[plan.id]),
            data=json.dumps({
                'student': self.student.id,
                'halaqa': self.halaqa.id,
                'start_date': timezone.localdate().isoformat(),
                'end_date': (timezone.localdate() + timedelta(days=10)).isoformat(),
                'target': 'خطة محدثة',
                'total_pages': 55,
                'notes': 'تم التحديث',
                'is_completed': False,
            }),
            content_type='application/json',
        )

        self.assertEqual(attendance_response.status_code, 200)
        self.assertEqual(plan_response.status_code, 200)

        attendance.refresh_from_db()
        plan.refresh_from_db()
        self.assertEqual(attendance.status, 'excused')
        self.assertEqual(attendance.notes, 'بعذر')
        self.assertEqual(plan.target, 'خطة محدثة')
        self.assertEqual(plan.total_pages, 55)
        self.assertEqual(plan.notes, 'تم التحديث')


    def test_point_and_memorization_endpoints_accept_explicit_dates(self):
        selected_date = timezone.localdate() - timedelta(days=2)

        point_response = self.client.post(reverse('halaqas:api:points-list'), data={
            'student': self.student.id,
            'halaqa': self.halaqa.id,
            'value': 9,
            'reason': 'نشاط مميز',
            'action_date': selected_date.isoformat(),
        })
        memorization_response = self.client.post(reverse('students:memorizationrecord-list'), data={
            'student': self.student.id,
            'surah': 'النساء',
            'from_verse': 3,
            'to_verse': 5,
            'evaluation': 'excellent',
            'date': selected_date.isoformat(),
            'is_approved': True,
        })

        self.assertEqual(point_response.status_code, 201)
        self.assertEqual(memorization_response.status_code, 201)
        self.assertEqual(PointTransaction.objects.latest('id').date.date(), selected_date)
        self.assertEqual(MemorizationRecord.objects.latest('id').date, selected_date)

    def test_extra_memorization_endpoint_accepts_page_only_recitation(self):
        response = self.client.post(reverse('students:memorizationrecord-list'), data={
            'student': self.student.id,
            'halaqa': self.halaqa.id,
            'recitation_type': 'extra',
            'pages': '12-14',
            'evaluation': 'excellent',
            'notes': 'قرأ صفحات إضافية',
            'is_approved': True,
        })

        self.assertEqual(response.status_code, 201)
        record = MemorizationRecord.objects.get(student=self.student, pages='12-14')
        self.assertEqual(record.recitation_type, 'extra')
        self.assertEqual(record.halaqa, self.halaqa)
        self.assertEqual(record.verses_count, 0)
        self.assertEqual(record.notes, 'قرأ صفحات إضافية')

    def test_homework_create_and_evaluate_endpoints_support_detail_page_flow(self):
        assigned_date = timezone.localdate() - timedelta(days=1)

        create_response = self.client.post(reverse('halaqas:api:homeworks-list'), data={
            'student': self.student.id,
            'halaqa': self.halaqa.id,
            'assigned_date': assigned_date.isoformat(),
            'expected_recitation_date': (assigned_date + timedelta(days=3)).isoformat(),
            'assignment_type': 'pages',
            'assignment_text': '',
            'pages': '12-14',
            'surah': 'الملك',
            'assignment_notes': 'مراجعة مع الإتقان',
        })

        self.assertEqual(create_response.status_code, 201)
        homework = Homework.objects.get(student=self.student, halaqa=self.halaqa)
        self.assertEqual(homework.assigned_date, assigned_date)
        self.assertEqual(homework.expected_recitation_date, assigned_date + timedelta(days=3))
        self.assertEqual(homework.assignment_type, 'pages')
        self.assertEqual(homework.pages, '12-14')
        self.assertEqual(homework.assignment_text, 'الصفحات 12-14')
        self.assertEqual(homework.surah, 'الملك')

        blocked_response = self.client.post(reverse('halaqas:api:homeworks-list'), data={
            'student': self.student.id,
            'halaqa': self.halaqa.id,
            'assigned_date': timezone.localdate().isoformat(),
            'assignment_type': 'pages',
            'assignment_text': 'الصفحات 8-9',
            'pages': '8-9',
        })

        self.assertEqual(blocked_response.status_code, 400)
        self.assertIn('على الطالب واجب غير منجز', str(blocked_response.json()))

        evaluate_response = self.client.patch(
            reverse('halaqas:api:homeworks-detail', args=[homework.id]),
            data=json.dumps({
                'student': self.student.id,
                'halaqa': self.halaqa.id,
                'evaluation_date': timezone.localdate().isoformat(),
                'evaluation': 'completed',
                'evaluation_notes': 'تم الإنجاز',
                'create_recitation_record': True,
                'recitation_pages': '12-14',
                'recitation_surah': 'الملك',
                'recitation_evaluation': 'very_good',
                'recitation_notes': 'تسميع الواجب',
            }),
            content_type='application/json',
        )

        self.assertEqual(evaluate_response.status_code, 200)
        homework.refresh_from_db()
        self.assertEqual(homework.evaluation, 'completed')
        self.assertEqual(homework.evaluation_notes, 'تم الإنجاز')

        linked_record = MemorizationRecord.objects.get(homework=homework)
        self.assertEqual(linked_record.student, self.student)
        self.assertEqual(linked_record.halaqa, self.halaqa)
        self.assertEqual(linked_record.recitation_type, 'homework')
        self.assertEqual(linked_record.pages, '12-14')
        self.assertEqual(linked_record.surah, 'الملك')
        self.assertIsNone(linked_record.from_verse)
        self.assertIsNone(linked_record.to_verse)
        self.assertEqual(linked_record.evaluation, 'very_good')
        self.assertEqual(linked_record.notes, 'تسميع الواجب')

        next_response = self.client.post(reverse('halaqas:api:homeworks-list'), data={
            'student': self.student.id,
            'halaqa': self.halaqa.id,
            'assigned_date': timezone.localdate().isoformat(),
            'assignment_type': 'pages',
            'assignment_text': '',
            'pages': '20',
            'surah': 'القلم',
        })

        self.assertEqual(next_response.status_code, 201)
        self.assertEqual(
            Homework.objects.filter(student=self.student, halaqa=self.halaqa, evaluation_date__isnull=True).count(),
            1,
        )

    def test_homework_assignment_uses_today_when_assigned_date_is_blank(self):
        response = self.client.post(reverse('halaqas:api:homeworks-list'), data={
            'student': self.student.id,
            'halaqa': self.halaqa.id,
            'assigned_date': '',
            'expected_recitation_date': '',
            'assignment_type': 'pages',
            'assignment_text': '',
            'pages': 'صفحة 8',
        })

        self.assertEqual(response.status_code, 201)
        homework = Homework.objects.get(student=self.student, halaqa=self.halaqa)
        self.assertEqual(homework.assigned_date, timezone.localdate())
        self.assertIsNone(homework.expected_recitation_date)


class MasterAdminDashboardTests(TestCase):
    def test_master_admin_dashboard_renders_with_empty_state(self):
        response = self.client.get('/halaqas/admin-dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'نظرة عامة')
        self.assertContains(response, 'التقارير')
        self.assertContains(response, 'لوحة الإدارة المركزية')

    def test_master_admin_dashboard_surfaces_teacher_entered_supervisory_data(self):
        teacher_user = User.objects.create_user(username='admin_teacher_source', password='StrongPass123!')
        teacher = Teacher.objects.create(
            user=teacher_user,
            full_name='أستاذ إشرافي',
            phone='0999111111',
        )
        parent = User.objects.create_user(username='admin_parent_source', password='StrongPass123!')
        halaqa = Halaqa.objects.create(name='حلقة الإشراف')
        halaqa.teachers.add(teacher)

        student = Student.objects.create(
            name='طالب إشرافي',
            birth_date='2012-02-02',
            parent=parent,
            parent_phone='0555000000',
            grade='ابتدائي رابع',
        )
        HalaqaMembership.objects.create(student=student, halaqa=halaqa, is_active=True)

        session = Session.objects.create(
            halaqa=halaqa,
            date=timezone.localdate(),
            start_time=time(15, 0),
            end_time=time(17, 0),
            notes='ملاحظة جلسة للإدارة',
        )
        Attendance.objects.create(
            session=session,
            student=student,
            status='present',
            notes='حضر في الوقت',
        )
        PointTransaction.objects.create(
            student=student,
            halaqa=halaqa,
            value=8,
            reason='مشاركة مميزة',
        )
        Plan.objects.create(
            student=student,
            halaqa=halaqa,
            start_date=timezone.localdate() - timedelta(days=1),
            end_date=timezone.localdate() + timedelta(days=7),
            target='إتقان سورة الملك',
            notes='متابعة يومية',
        )
        Homework.objects.create(
            student=student,
            halaqa=halaqa,
            assigned_date=timezone.localdate(),
            assignment_type='surah',
            assignment_text='سورة الملك',
            assignment_notes='مراجعة مع الإتقان',
            evaluation='completed',
            evaluation_date=timezone.localdate(),
            evaluation_notes='تم الإنجاز',
        )
        MemorizationRecord.objects.create(
            student=student,
            surah='الملك',
            from_verse=1,
            to_verse=10,
            date=timezone.localdate(),
            evaluation='excellent',
        )

        response = self.client.get(f'/halaqas/admin-dashboard/?halaqa={halaqa.id}&focus_student={student.id}')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'إشراف الطلاب بالتفصيل')
        self.assertContains(response, 'طالب إشرافي')
        self.assertContains(response, 'إتقان سورة الملك')
        self.assertContains(response, 'سورة الملك')
        self.assertContains(response, 'مشاركة مميزة')
        self.assertContains(response, 'ملاحظة جلسة للإدارة')

    def test_master_admin_dashboard_supports_formal_category_reporting_and_custom_filters(self):
        Category.seed_official_categories()
        category_two = Category.objects.get(code='2')
        category_five = Category.objects.get(code='5')
        today = timezone.localdate()
        range_start = today - timedelta(days=6)
        old_date = today - timedelta(days=40)

        parent_one = User.objects.create_user(username='category_parent_one', password='StrongPass123!')
        parent_two = User.objects.create_user(username='category_parent_two', password='StrongPass123!')
        parent_three = User.objects.create_user(username='category_parent_three', password='StrongPass123!')

        halaqa_two = Halaqa.objects.create(name='حلقة الفئة الثانية', category=category_two)
        halaqa_five = Halaqa.objects.create(name='حلقة الفئة الخامسة', category=category_five)
        unresolved_halaqa = Halaqa.objects.create(name='حلقة غير محسومة')

        student_two = Student.objects.create(
            name='طالب الفئة الثانية',
            birth_date='2013-03-03',
            parent=parent_one,
            parent_phone='0777111000',
            grade='ابتدائي خامس',
        )
        student_five = Student.objects.create(
            name='طالب الفئة الخامسة',
            birth_date='2010-04-04',
            parent=parent_two,
            parent_phone='0777111001',
            grade='ثانوي عاشر',
        )
        unresolved_student = Student.objects.create(
            name='طالب غير محسوم',
            birth_date='2007-05-05',
            parent=parent_three,
            parent_phone='0777111002',
            halaqa=unresolved_halaqa,
        )

        HalaqaMembership.objects.create(student=student_two, halaqa=halaqa_two, is_active=True)
        HalaqaMembership.objects.create(student=student_five, halaqa=halaqa_five, is_active=True)

        session_two = Session.objects.create(
            halaqa=halaqa_two,
            date=today,
            start_time=time(15, 0),
            end_time=time(17, 0),
        )
        session_five = Session.objects.create(
            halaqa=halaqa_five,
            date=today,
            start_time=time(15, 0),
            end_time=time(17, 0),
        )
        Attendance.objects.create(
            session=session_two,
            student=student_two,
            status='present',
            notes='حضور ممتاز',
        )
        Attendance.objects.create(
            session=session_five,
            student=student_five,
            status='absent',
            notes='غياب يحتاج متابعة',
        )

        PointTransaction.objects.create(
            student=student_two,
            halaqa=halaqa_two,
            value=12,
            reason='تفوق يومي',
            date=timezone.make_aware(
                timezone.datetime.combine(today, time(12, 0)),
                timezone.get_current_timezone(),
            ),
        )
        PointTransaction.objects.create(
            student=student_five,
            halaqa=halaqa_five,
            value=2,
            reason='مشاركة محدودة',
            date=timezone.make_aware(
                timezone.datetime.combine(today, time(13, 0)),
                timezone.get_current_timezone(),
            ),
        )
        PointTransaction.objects.create(
            student=student_five,
            halaqa=halaqa_five,
            value=50,
            reason='خارج النطاق الحالي',
            date=timezone.make_aware(
                timezone.datetime.combine(old_date, time(10, 0)),
                timezone.get_current_timezone(),
            ),
        )

        Plan.objects.create(
            student=student_two,
            halaqa=halaqa_two,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=7),
            target='خطة الفئة الثانية',
            notes='متابعة مستمرة',
        )
        Homework.objects.create(
            student=student_two,
            halaqa=halaqa_two,
            assigned_date=today,
            assignment_type='surah',
            assignment_text='سورة الملك',
            assignment_notes='بانتظار التقييم',
        )

        MemorizationRecord.objects.create(
            student=student_two,
            surah='الملك',
            from_verse=1,
            to_verse=8,
            date=today,
            evaluation='excellent',
        )
        MemorizationRecord.objects.create(
            student=student_five,
            surah='النبأ',
            from_verse=1,
            to_verse=3,
            date=today,
            evaluation='needs_followup',
        )

        response = self.client.get(
            reverse('halaqas:master_admin_dashboard'),
            {
                'range': 'custom',
                'start_date': range_start.isoformat(),
                'end_date': today.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'تقارير الفئات الرسمية')
        self.assertContains(response, category_two.name)
        self.assertContains(response, 'حالات تصنيف غير محسومة')
        self.assertEqual(
            response.context['date_window_label'],
            f'{range_start:%Y-%m-%d} - {today:%Y-%m-%d}',
        )
        self.assertEqual(response.context['category_attendance_ranking'][0]['name'], category_two.name)
        self.assertEqual(response.context['category_memorization_ranking'][0]['name'], category_two.name)
        self.assertEqual(response.context['category_points_ranking'][0]['name'], category_two.name)
        category_five_points = next(
            row for row in response.context['category_points_ranking'] if row['name'] == category_five.name
        )
        self.assertEqual(category_five_points['points_in_range'], 2)
        self.assertEqual(category_five_points['points_total'], 52)
        self.assertGreater(response.context['category_foundation']['missing_count'], 0)
        self.assertTrue(
            any(option['value'] == '__unresolved__' for option in response.context['filter_options']['categories'])
        )

        filtered_response = self.client.get(
            reverse('halaqas:master_admin_dashboard'),
            {
                'range': 'custom',
                'start_date': range_start.isoformat(),
                'end_date': today.isoformat(),
                'category': str(category_two.id),
                'student': str(student_two.id),
            },
        )

        self.assertEqual(filtered_response.status_code, 200)
        self.assertEqual(filtered_response.context['filters']['category'], str(category_two.id))
        self.assertEqual(filtered_response.context['filters']['student'], str(student_two.id))
        self.assertEqual(len(filtered_response.context['student_supervision_rows']), 1)
        self.assertEqual(filtered_response.context['student_supervision_rows'][0]['id'], student_two.id)

        export_csv_response = self.client.get(
            reverse('halaqas:master_admin_dashboard_export'),
            {
                'format': 'csv',
                'report': 'student_reports',
                'level': 'detailed',
                'range': 'custom',
                'start_date': range_start.isoformat(),
                'end_date': today.isoformat(),
                'category': str(category_two.id),
            },
        )

        self.assertEqual(export_csv_response.status_code, 200)
        self.assertIn('text/csv', export_csv_response['Content-Type'])
        export_csv_text = export_csv_response.content.decode('utf-8-sig')
        self.assertIn(student_two.name, export_csv_text)
        self.assertNotIn(student_five.name, export_csv_text)
        self.assertIn('إشراف الطلاب بالتفصيل', export_csv_text)

        export_print_response = self.client.get(
            reverse('halaqas:master_admin_dashboard_export'),
            {
                'format': 'pdf',
                'report': 'current_view',
                'current_panel': 'reportsPanel',
                'level': 'summary',
                'range': 'custom',
                'start_date': range_start.isoformat(),
                'end_date': today.isoformat(),
            },
        )

        self.assertEqual(export_print_response.status_code, 200)
        self.assertContains(export_print_response, 'طباعة / حفظ PDF')
        self.assertContains(export_print_response, category_two.name)
        self.assertContains(export_print_response, 'هذا العرض مهيأ للطباعة')
