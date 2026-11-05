from django.test import TestCase
from accounts.models import User
from django.urls import reverse
from urllib.parse import urlsplit, parse_qs

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
        sliced_login_url = response.url.partition("?")
        self.assertEqual(sliced_login_url[0], reverse('login'))

    def test_owner_can_open_settings(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/profile_settings.html")
        self.assertEqual(response.context["profile_user"].pk, self.owner.pk)
        # self.assertIn("avatar_form", response.context)

    def test_other_user_gets_their_own_settings(self):
        self.client.force_login(self.alien)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/profile_settings.html")
        self.assertEqual(response.context["profile_user"].pk, self.alien.pk)


    