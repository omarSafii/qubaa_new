import os
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

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
