from rest_framework.test import APITestCase
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

class MeDisplayNameTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="profile-settings-owner", 
            name="test-site-owner", 
            about="I love watch Anime", 
            email="profile-settings-owner@example.com")
        cls.other = User.objects.create_user(
            username="profile-settings-other", 
            name="test-site-other",
            email="profile-settings-other@example.com",
            )

    def setUp(self):
        self.url = reverse("accounts:me")
        self.client.force_authenticate(user=self.owner)

    def test_get_returns_display_name(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("name"), self.owner.name)

    def test_patch_name_trims_edges_and_preserves_other_fields(self):
        response = self.client.patch(
            self.url, {"name": "   Новый ник   "}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("name"), "Новый ник")
        self.assertEqual(response.data.get("username"), self.owner.username)
        self.assertEqual(response.data.get("about"), self.owner.about)

    def test_name_can_be_cleared(self):
        self.skipTest('')

    def test_display_names_need_not_be_unique(self):
        self.skipTest('')

    def test_64_character_name_is_accepted(self):
        self.skipTest('')

    def test_65_character_name_rejects_entire_patch(self):
        self.skipTest('')

    def test_null_name_is_rejected(self):
        self.skipTest('')
