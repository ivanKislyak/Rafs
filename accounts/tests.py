from django.test import TestCase
from django.urls import reverse
from accounts.models import User

class RegistrationEmailTests(TestCase):

    def test_registration_with_unique_email_succeds(self):
        User.objects.create
