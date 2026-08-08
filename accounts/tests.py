from django.test import TestCase
from django.urls import reverse
from accounts.models import User

class RegistrationEmailTests(TestCase):

    def test_registration_with_unique_email_succeds(self):
        initial_user_count = User.objects.count()

        payload = {
            "email": "realunique@example.com",
            "username": "new_user",
            "password1": "strongpassword123", 
            "password2": "strongpassword123",
        }

        url = reverse('accounts:register')
        response = self.client.post(url, data=payload)

        self.assertEqual(response.status_code, 302) 

        self.assertEqual(User.objects.count(), initial_user_count + 1)
        self.assertTrue(User.objects.filter(email="realunique@example.com").exists())
