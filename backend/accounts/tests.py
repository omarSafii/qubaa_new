import os
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from halaqas.models import Halaqa, Teacher
from .models import Profile


class CurrentUserEndpointTests(TestCase):
    def test_current_user_endpoint_returns_profile_role(self):
        user = get_user_model().objects.create_user(
            username='teacher_user',
            password='StrongPass123!',
        )
        user.profile.role = 'teacher'
        user.profile.save()

        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get('/api/users/me/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['username'], 'teacher_user')
        self.assertEqual(response.json()['role'], 'teacher')


class UserProfileSignalTests(TestCase):
    def test_login_recreates_missing_profile_instead_of_crashing(self):
        user = get_user_model().objects.create_user(
            username='admin_like_user',
            password='StrongPass123!',
            is_staff=True,
            is_superuser=True,
        )
        Profile.objects.filter(user=user).delete()

        login_succeeded = self.client.login(
            username='admin_like_user',
            password='StrongPass123!',
        )

        self.assertTrue(login_succeeded)
        self.assertTrue(Profile.objects.filter(user=user).exists())


class TeacherSessionLoginTests(TestCase):
    def create_teacher(self, username='teacher_user', full_name='Teacher User'):
        user = get_user_model().objects.create_user(
            username=username,
            password='StrongPass123!',
        )
        user.profile.role = 'teacher'
        user.profile.save(update_fields=['role'])
        teacher = Teacher.objects.create(user=user, full_name=full_name, phone=f'09{user.pk:08d}')
        halaqa = Halaqa.objects.create(name=f'{full_name} Halaqa')
        halaqa.teachers.add(teacher)
        return user, teacher, halaqa

    def create_supervisor(self, username='supervisor_user'):
        user = get_user_model().objects.create_user(
            username=username,
            password='StrongPass123!',
        )
        user.profile.role = 'supervisor'
        user.profile.save(update_fields=['role'])
        return user

    def test_anonymous_login_page_displays_form(self):
        response = self.client.get(reverse('login'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'تسجيل الدخول')
        self.assertContains(response, 'autocomplete="username"')
        self.assertContains(response, 'autocomplete="current-password"')

    def test_teacher_login_redirects_to_single_assigned_halaqa(self):
        user = get_user_model().objects.create_user(
            username='single_teacher',
            password='StrongPass123!',
        )
        user.profile.role = 'teacher'
        user.profile.save(update_fields=['role'])
        teacher = Teacher.objects.create(user=user, full_name='Single Teacher', phone='0999000001')
        halaqa = Halaqa.objects.create(name='Single Login Halaqa')
        halaqa.teachers.add(teacher)

        response = self.client.post(reverse('login'), {
            'username': 'single_teacher',
            'password': 'StrongPass123!',
        })

        self.assertRedirects(response, reverse('halaqas:halaqa_detail', args=[halaqa.pk]), fetch_redirect_response=False)

    def test_teacher_can_login_with_full_name(self):
        user = get_user_model().objects.create_user(
            username='teacher_001',
            password='StrongPass123!',
        )
        user.profile.role = 'teacher'
        user.profile.save(update_fields=['role'])
        teacher = Teacher.objects.create(user=user, full_name='Teacher Full Name', phone='0999000003')
        halaqa = Halaqa.objects.create(name='Full Name Login Halaqa')
        halaqa.teachers.add(teacher)

        response = self.client.post(reverse('login'), {
            'username': 'Teacher Full Name',
            'password': 'StrongPass123!',
        })

        self.assertRedirects(response, reverse('halaqas:halaqa_detail', args=[halaqa.pk]), fetch_redirect_response=False)

    def test_invalid_login_stays_on_page_with_arabic_error(self):
        response = self.client.post(reverse('login'), {
            'username': 'missing_teacher',
            'password': 'WrongPass123!',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'اسم الأستاذ أو كلمة المرور غير صحيحة.')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_authenticated_teacher_opening_login_redirects_without_loop(self):
        user, _teacher, halaqa = self.create_teacher('active_teacher', 'Active Teacher')
        self.client.force_login(user)

        response = self.client.get(reverse('login'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('halaqas:halaqa_detail', args=[halaqa.pk]))
        self.assertNotEqual(response.url, reverse('login'))

    def test_teacher_session_is_persistent_for_configured_age(self):
        _user, _teacher, _halaqa = self.create_teacher('persistent_teacher', 'Persistent Teacher')

        self.client.post(reverse('login'), {
            'username': 'persistent_teacher',
            'password': 'StrongPass123!',
        })

        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertAlmostEqual(
            self.client.session.get_expiry_age(),
            settings.SESSION_COOKIE_AGE,
            delta=5,
        )
        self.assertGreaterEqual(settings.SESSION_COOKIE_AGE, 60 * 60 * 24 * 30)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)

    def test_anonymous_teacher_page_redirects_to_login(self):
        _user, _teacher, halaqa = self.create_teacher('protected_teacher', 'Protected Teacher')

        response = self.client.get(reverse('halaqas:halaqa_detail', args=[halaqa.pk]))

        expected = f"{reverse('login')}?next={reverse('halaqas:halaqa_detail', args=[halaqa.pk])}"
        self.assertRedirects(response, expected, fetch_redirect_response=False)

    def test_teacher_cannot_access_another_teachers_halaqa(self):
        user, _teacher, _halaqa = self.create_teacher('first_teacher', 'First Teacher')
        _other_user, _other_teacher, other_halaqa = self.create_teacher('second_teacher', 'Second Teacher')
        self.client.force_login(user)

        response = self.client.get(reverse('halaqas:halaqa_detail', args=[other_halaqa.pk]))

        self.assertEqual(response.status_code, 403)

    def test_logout_post_flushes_session_and_protects_teacher_page(self):
        user, _teacher, halaqa = self.create_teacher('logout_teacher', 'Logout Teacher')
        self.client.force_login(user)

        response = self.client.post(reverse('logout'))

        self.assertRedirects(response, reverse('login'), fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)
        protected_response = self.client.get(reverse('halaqas:halaqa_detail', args=[halaqa.pk]))
        self.assertEqual(protected_response.status_code, 302)
        self.assertTrue(protected_response.url.startswith(reverse('login')))

    def test_logout_rejects_get(self):
        user, _teacher, _halaqa = self.create_teacher('get_logout_teacher', 'Get Logout Teacher')
        self.client.force_login(user)

        response = self.client.get(reverse('logout'))

        self.assertEqual(response.status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)

    def test_quran_icon_is_logout_trigger_on_teacher_page_without_old_text_button(self):
        user, _teacher, halaqa = self.create_teacher('icon_teacher', 'Icon Teacher')
        self.client.force_login(user)

        response = self.client.get(reverse('halaqas:halaqa_detail', args=[halaqa.pk]))

        self.assertContains(response, 'data-logout-trigger')
        self.assertContains(response, 'title="تسجيل الخروج"')
        self.assertContains(response, 'هل أنت متأكد أنك تريد تسجيل الخروج؟')
        self.assertNotContains(response, 'btn-outline-light')

    def test_logout_cancel_control_is_client_side_and_does_not_end_session(self):
        user, _teacher, halaqa = self.create_teacher('cancel_teacher', 'Cancel Teacher')
        self.client.force_login(user)

        response = self.client.get(reverse('halaqas:halaqa_detail', args=[halaqa.pk]))

        self.assertContains(response, 'data-logout-cancel')
        self.assertContains(response, 'type="button" data-logout-cancel')
        self.assertIn('_auth_user_id', self.client.session)

    def test_quran_icon_is_logout_trigger_on_custom_admin_page(self):
        admin = get_user_model().objects.create_user(
            username='icon_admin',
            password='StrongPass123!',
            is_staff=True,
        )
        self.client.force_login(admin)

        response = self.client.get(reverse('halaqas:master_admin_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-logout-trigger')
        self.assertContains(response, 'هل أنت متأكد أنك تريد تسجيل الخروج؟')

    def test_quran_icon_is_logout_trigger_on_teacher_halaqa_selection_page(self):
        user = get_user_model().objects.create_user(
            username='selection_teacher',
            password='StrongPass123!',
        )
        user.profile.role = 'teacher'
        user.profile.save(update_fields=['role'])
        teacher = Teacher.objects.create(user=user, full_name='Selection Teacher', phone='0999000011')
        first_halaqa = Halaqa.objects.create(name='Teacher Selection Halaqa One')
        second_halaqa = Halaqa.objects.create(name='Teacher Selection Halaqa Two')
        first_halaqa.teachers.add(teacher)
        Halaqa.teachers.through.objects.create(teacher_id=teacher.pk, halaqa_id=second_halaqa.pk)
        self.client.force_login(user)

        response = self.client.get(reverse('teacher_halaqas'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-logout-trigger')
        self.assertContains(response, 'title="تسجيل الخروج"')
        self.assertContains(response, 'هل أنت متأكد أنك تريد تسجيل الخروج؟')
        self.assertNotContains(response, 'btn-outline-light')

    def test_quran_icon_is_logout_trigger_on_supervisor_dashboard(self):
        supervisor = self.create_supervisor('icon_supervisor')
        self.client.force_login(supervisor)

        response = self.client.get(reverse('halaqas:supervisor_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-logout-trigger')
        self.assertContains(response, 'title="تسجيل الخروج"')
        self.assertContains(response, 'هل أنت متأكد أنك تريد تسجيل الخروج؟')
        self.assertNotContains(response, 'btn-outline-light')

    def test_logout_requires_csrf_token(self):
        user, _teacher, halaqa = self.create_teacher('csrf_logout_teacher', 'CSRF Logout Teacher')
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(user)

        missing_token_response = csrf_client.post(reverse('logout'))

        self.assertEqual(missing_token_response.status_code, 403)
        self.assertIn('_auth_user_id', csrf_client.session)

        page_response = csrf_client.get(reverse('halaqas:halaqa_detail', args=[halaqa.pk]))
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, 'csrfmiddlewaretoken')

        csrf_token = csrf_client.cookies['csrftoken'].value
        response = csrf_client.post(
            reverse('logout'),
            {'csrfmiddlewaretoken': csrf_token},
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertRedirects(response, reverse('login'), fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', csrf_client.session)

    def test_admin_and_supervisor_login_redirects_are_unchanged(self):
        admin = get_user_model().objects.create_user(
            username='login_admin',
            password='StrongPass123!',
            is_staff=True,
        )
        supervisor = get_user_model().objects.create_user(
            username='login_supervisor',
            password='StrongPass123!',
        )
        supervisor.profile.role = 'supervisor'
        supervisor.profile.save(update_fields=['role'])

        admin_response = self.client.post(reverse('login'), {
            'username': admin.username,
            'password': 'StrongPass123!',
        })
        self.assertRedirects(
            admin_response,
            reverse('halaqas:master_admin_dashboard'),
            fetch_redirect_response=False,
        )
        self.client.logout()
        supervisor_response = self.client.post(reverse('login'), {
            'username': supervisor.username,
            'password': 'StrongPass123!',
        })
        self.assertRedirects(
            supervisor_response,
            reverse('halaqas:supervisor_dashboard'),
            fetch_redirect_response=False,
        )

    def test_external_next_url_is_not_used(self):
        user, _teacher, halaqa = self.create_teacher('safe_next_teacher', 'Safe Next Teacher')

        response = self.client.post(f"{reverse('login')}?next=https://example.net/", {
            'username': user.username,
            'password': 'StrongPass123!',
            'next': 'https://example.net/',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('halaqas:halaqa_detail', args=[halaqa.pk]))

    def test_teacher_with_multiple_halaqas_sees_only_assigned_halaqas(self):
        user = get_user_model().objects.create_user(
            username='multi_teacher',
            password='StrongPass123!',
        )
        user.profile.role = 'teacher'
        user.profile.save(update_fields=['role'])
        teacher = Teacher.objects.create(user=user, full_name='Multi Teacher', phone='0999000002')
        first_halaqa = Halaqa.objects.create(name='Multi Login Halaqa One')
        second_halaqa = Halaqa.objects.create(name='Multi Login Halaqa Two')
        other_halaqa = Halaqa.objects.create(name='Unassigned Login Halaqa')
        first_halaqa.teachers.add(teacher)
        Halaqa.teachers.through.objects.create(teacher_id=teacher.pk, halaqa_id=second_halaqa.pk)

        response = self.client.post(reverse('login'), {
            'username': 'multi_teacher',
            'password': 'StrongPass123!',
        })

        self.assertRedirects(response, reverse('teacher_halaqas'), fetch_redirect_response=False)
        list_response = self.client.get(reverse('teacher_halaqas'))
        self.assertContains(list_response, first_halaqa.name)
        self.assertContains(list_response, second_halaqa.name)
        self.assertNotContains(list_response, other_halaqa.name)


class EnsureSuperuserCommandTests(TestCase):
    def test_creates_superuser_from_environment(self):
        out = StringIO()

        with patch.dict(
            os.environ,
            {
                'DJANGO_SUPERUSER_USERNAME': 'hamza',
                'DJANGO_SUPERUSER_EMAIL': 'hamza@gmail.com',
                'DJANGO_SUPERUSER_PASSWORD': 'Hamza@123',
                'DJANGO_SUPERUSER_RESET_PASSWORD': '0',
            },
            clear=False,
        ):
            call_command('ensure_superuser', stdout=out)

        user = get_user_model().objects.get(username='hamza')
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password('Hamza@123'))
        self.assertEqual(user.email, 'hamza@gmail.com')
        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_resets_existing_superuser_password_when_enabled(self):
        user = get_user_model().objects.create_superuser(
            username='hamza',
            email='old@example.com',
            password='OldPass123!',
        )
        user.set_password('OldPass123!')
        user.save()
        Profile.objects.filter(user=user).delete()
        out = StringIO()

        with patch.dict(
            os.environ,
            {
                'DJANGO_SUPERUSER_USERNAME': 'hamza',
                'DJANGO_SUPERUSER_EMAIL': 'hamza@gmail.com',
                'DJANGO_SUPERUSER_PASSWORD': 'Hamza@123',
                'DJANGO_SUPERUSER_RESET_PASSWORD': '1',
            },
            clear=False,
        ):
            call_command('ensure_superuser', stdout=out)

        user.refresh_from_db()
        self.assertTrue(user.check_password('Hamza@123'))
        self.assertEqual(user.email, 'hamza@gmail.com')
        self.assertTrue(Profile.objects.filter(user=user).exists())
