from django.test import TestCase
from accounts.models import User
from django.urls import reverse

class ProfileSettingsPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="profile-settings-owner", email="profile-settings-owner@example.com")
        cls.alien = User.objects.create_user(username="profile-settings-alien", email="profile-settings-alien@example.com")

    def setUp(self):
        self.url = reverse("profile_settings")

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_owner_can_open_settings(self):
        self.skipTest("TODO: Implement owner settings test")

    def test_other_users_settings_are_forbidden(self):
        self.skipTest("TODO: Implement other users' settings forbidden test")

    def test_unknown_users_settings_return_404(self):
        self.skipTest("TODO: Implement unknown user settings 404 test")