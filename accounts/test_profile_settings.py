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
        owner_qs = User.objects.get(pk=self.owner.pk)
        other_qs = User.objects.get(pk=self.other.pk)
        response = self.client.patch(
            self.url, {"name": "   Новый ник   "}, format="json"
        )
        owner_qs.refresh_from_db()
        other_qs.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("name"), "Новый ник")
        self.assertEqual(response.data.get("username"), self.owner.username)
        self.assertEqual(response.data.get("about"), self.owner.about)
        self.assertEqual(owner_qs.username, self.owner.username)
        self.assertEqual(owner_qs.name, "Новый ник")
        self.assertEqual(owner_qs.about, self.owner.about)
        self.assertEqual(other_qs.username, self.other.username)
        self.assertEqual(other_qs.name, self.other.name)

    def test_patch_preserves_name_when_omitted(self):
        owner_qs = User.objects.get(pk=self.owner.pk)
        response = self.client.patch(
            self.url, {"about": "I hate Series"}, format="json"
        )
        owner_qs.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(owner_qs.name, self.owner.name)
        self.assertEqual(owner_qs.username, self.owner.username)
        self.assertEqual(response.data.get("name"), self.owner.name)

    def test_name_can_be_cleared(self):
        owner_qs = User.objects.get(pk=self.owner.pk)
        response = self.client.patch(
            self.url, {"name": ""}, format="json"
        )
        owner_qs.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("name"), "")
        self.assertEqual(owner_qs.name, "")

    def test_display_names_need_not_be_unique(self):
        owner_qs = User.objects.get(pk=self.owner.pk)
        other_qs = User.objects.get(pk=self.other.pk)
        response = self.client.patch(
            self.url,
            {"name": self.other.name}, 
            format="json"
        )
        owner_qs.refresh_from_db()
        other_qs.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("username"), owner_qs.username)
        self.assertEqual(other_qs.username, self.other.username)
        self.assertEqual(owner_qs.name, self.other.name)
        self.assertEqual(other_qs.name, self.other.name)        

    def test_64_character_name_is_accepted(self):
        string_64 = "t"*64
        response = self.client.patch(
            self.url, {"name": string_64}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        owner_qs = User.objects.get(pk=self.owner.pk)
        self.assertEqual(owner_qs.name, string_64)

    def test_65_character_name_rejects_entire_patch(self):
        string_65 = "t"*65
        first_owner_qs = User.objects.get(pk=self.owner.pk)
        response = self.client.patch(
            self.url, {
                "name": string_65,
                "about": "new_about"}, format="json"
        )
        
        second_owner_qs = User.objects.get(pk=self.owner.pk)
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)
        self.assertEqual(first_owner_qs.name, second_owner_qs.name)
        self.assertEqual(first_owner_qs.about, second_owner_qs.about)

    def test_null_name_is_rejected(self):
        first_owner_qs = User.objects.get(pk=self.owner.pk)
        response = self.client.patch(
            self.url, 
            {"name": None}, 
            format="json"
        )
        
        second_owner_qs = User.objects.get(pk=self.owner.pk)
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)
        self.assertEqual(first_owner_qs.name, second_owner_qs.name)

