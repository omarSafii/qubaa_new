from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


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
