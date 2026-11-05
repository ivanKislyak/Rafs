from rest_framework.test import APITestCase
from django.test import TestCase
from accounts.models import User
from django.urls import reverse
from urllib.parse import urlsplit, parse_qs
from html.parser import HTMLParser
from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APIClient

from accounts.forms import AvatarUpdateForm

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
        self.assertIsInstance(response.context["avatar_form"], AvatarUpdateForm)
        self.assertEqual(response.context["avatar_form"].instance.pk, self.owner.pk)

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



class UsernameSettingsTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='username-owner', email='username-owner@example.com', name='Public name', about='Keep this')
        cls.other = User.objects.create_user(username='username-other', email='username-other@example.com', name='Other name')

    def setUp(self):
        self.url = reverse('accounts:me-username')
        self.client.force_login(self.owner)

    def test_get_returns_current_username_and_profile_url(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'username': self.owner.username, 'profile_url': reverse('profile', args=[self.owner.username])})

    def test_patch_renames_same_account_keeps_session_and_replaces_public_url(self):
        old_url = reverse('profile', args=[self.owner.username])
        response = self.client.patch(self.url, {'username': 'new_username'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.owner.refresh_from_db()
        new_url = reverse('profile', args=['new_username'])
        self.assertEqual(response.json(), {'username': 'new_username', 'profile_url': new_url})
        self.assertEqual(self.owner.username, 'new_username')
        self.assertEqual(self.owner.name, 'Public name')
        self.assertEqual(self.owner.about, 'Keep this')
        profile = self.client.get(new_url)
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.context['profile_user'].pk, self.owner.pk)
        self.assertTrue(profile.context['is_owner'])
        self.assertEqual(self.client.get(old_url).status_code, 404)
        settings = self.client.get(reverse('profile_settings'))
        self.assertEqual(settings.status_code, 200)
        self.assertContains(settings, f'href="{new_url}"')
        self.assertNotContains(settings, f'href="{old_url}"')

    def test_current_name_can_be_submitted_again(self):
        response = self.client.patch(self.url, {'username': self.owner.username}, format='json')
        self.assertEqual(response.status_code, 200)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.username, 'username-owner')

    def test_taken_name_is_field_error_and_neither_account_changes(self):
        response = self.client.patch(self.url, {'username': self.other.username}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('username', response.json())
        self.owner.refresh_from_db(); self.other.refresh_from_db()
        self.assertEqual(self.owner.username, 'username-owner')
        self.assertEqual(self.other.username, 'username-other')

    def test_invalid_names_preserve_database(self):
        for username in ('', ' \t\n', 'invalid name', 'invalid/name', 'bad!', 'x' * 151, None, ['list'], {'object':'value'}):
            with self.subTest(username=username):
                response = self.client.patch(self.url, {'username': username}, format='json')
                self.assertEqual(response.status_code, 400)
                self.assertIn('username', response.json())
                self.owner.refresh_from_db()
                self.assertEqual(self.owner.username, 'username-owner')

    def test_model_unicode_validator_is_preserved(self):
        response = self.client.patch(self.url, {'username':'Новый_ник'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['profile_url'], reverse('profile', args=['Новый_ник']))
        self.assertEqual(self.client.get(response.json()['profile_url']).status_code, 200)

    def test_anonymous_get_and_patch_are_denied(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.patch(self.url, {'username':'anonymous-change'}, format='json').status_code, 403)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.username, 'username-owner')

    def test_client_id_and_other_fields_cannot_target_or_modify_another_account(self):
        response = self.client.patch(self.url, {'id':self.other.pk, 'username':'owner-renamed', 'name':'Not allowed', 'about':'Not allowed', 'email':'not-allowed@example.com', 'is_staff':True, 'profile_url':'https://example.com/'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.owner.refresh_from_db(); self.other.refresh_from_db()
        self.assertEqual(self.owner.username, 'owner-renamed')
        self.assertEqual(self.owner.name, 'Public name')
        self.assertEqual(self.owner.about, 'Keep this')
        self.assertEqual(self.owner.email, 'username-owner@example.com')
        self.assertFalse(self.owner.is_staff)
        self.assertEqual(self.other.username, 'username-other')
        self.assertEqual(self.other.name, 'Other name')
        self.assertEqual(response.json()['profile_url'], reverse('profile', args=['owner-renamed']))

    def test_only_get_patch_head_options_are_allowed(self):
        for method in ('put','post','delete'):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(self.url, {'username':'forbidden'}, format='json').status_code, 405)
        self.assertEqual(self.client.head(self.url).status_code, 200)
        self.assertEqual(self.client.options(self.url).status_code, 200)

    def test_session_patch_requires_csrf_from_settings_form(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.patch(self.url, {'username':'csrf-name'}, format='json').status_code, 403)
        response = client.get(reverse('profile_settings'))
        class Tokens(HTMLParser):
            token = None
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'input' and attrs.get('name') == 'csrfmiddlewaretoken':
                    self.token = attrs['value']
        parser = Tokens(); parser.feed(response.content.decode())
        self.assertTrue(parser.token)
        response = client.patch(self.url, {'username':'csrf-name'}, format='json', HTTP_X_CSRFTOKEN=parser.token)
        self.assertEqual(response.status_code, 200)


class SettingsIntegrationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='settings-integration', email='settings@example.com', name='<Display & name>', about='First line\n<not HTML>')
        self.other = User.objects.create_user(username='settings-visitor', email='settings-visitor@example.com')
        self.client.force_login(self.owner)
        self.url = reverse('profile_settings')

    def test_settings_forms_and_avatar_instance_belong_to_request_user(self):
        response = self.client.get(self.url, {'id':self.other.pk})
        self.assertEqual(response.context['profile_user'].pk, self.owner.pk)
        self.assertEqual(response.context['avatar_form'].instance.pk, self.owner.pk)
        for name in ('accounts:me', 'accounts:me-username', 'accounts:update-avatar'):
            self.assertContains(response, f'action="{reverse(name)}"')
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'name="return_to" value="settings"')
        self.assertContains(response, 'value="&lt;Display &amp; name&gt;"')
        self.assertContains(response, 'First line\n&lt;not HTML&gt;')
        self.assertNotContains(response, self.other.email)

    def test_public_heading_uses_escaped_display_name_then_username_fallback(self):
        url = reverse('profile', args=[self.owner.username])
        response = self.client.get(url)
        self.assertContains(response, '<h1 id="profile-name">&lt;Display &amp; name&gt;</h1>', html=True)
        self.owner.name = ''; self.owner.save(update_fields=['name'])
        response = self.client.get(url)
        self.assertContains(response, f'<h1 id="profile-name">{self.owner.username}</h1>', html=True)

    def test_only_owner_has_settings_link_and_old_editor_remains(self):
        url = reverse('profile', args=[self.owner.username])
        response = self.client.get(url)
        self.assertContains(response, f'href="{self.url}"')
        self.assertContains(response, 'data-profile-editor')
        self.assertContains(response, 'accounts/js/profile-edit.js')
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(url), f'href="{self.url}"')
        self.client.logout()
        self.assertNotContains(self.client.get(url), f'href="{self.url}"')


class SettingsAvatarTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.directory.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.owner = User.objects.create_user(username='settings-avatar', email='settings-avatar@example.com')
        self.client.force_login(self.owner)
        self.url = reverse('accounts:update-avatar')

    @staticmethod
    def image():
        output = BytesIO()
        Image.new('RGB', (20,30), 'purple').save(output, format='PNG')
        return SimpleUploadedFile('avatar.png', output.getvalue(), content_type='image/png')

    def test_upload_and_remove_from_settings_return_to_settings(self):
        response = self.client.post(self.url, {'return_to':'settings', 'avatar_image':self.image()})
        self.assertRedirects(response, reverse('profile_settings'))
        self.owner.refresh_from_db()
        image = self.owner.avatar_image
        self.assertTrue(image.storage.exists(image.name))
        response = self.client.post(self.url, {'return_to':'settings','avatar_action':'delete'})
        self.assertRedirects(response, reverse('profile_settings'))
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.avatar_image)
        self.assertFalse(image.storage.exists(image.name))

    def test_old_profile_upload_and_delete_still_return_to_profile(self):
        for payload in ({'avatar_image':self.image()}, {'avatar_action':'delete'}):
            response = self.client.post(self.url, payload)
            self.assertRedirects(response, reverse('profile', args=[self.owner.username]))

    def test_invalid_upload_retains_avatar_and_reports_error_in_settings(self):
        self.client.post(self.url, {'avatar_image':self.image()})
        self.owner.refresh_from_db()
        old_name = self.owner.avatar_image.name
        invalid = SimpleUploadedFile('bad.png', b'not an image', content_type='image/png')
        response = self.client.post(self.url, {'return_to':'settings','avatar_image':invalid}, follow=True)
        self.assertEqual(response.redirect_chain, [(reverse('profile_settings'),302)])
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.avatar_image.name, old_name)
        self.assertTrue(self.owner.avatar_image.storage.exists(old_name))
        self.assertContains(response, 'data-toast-tags="error"')

    def test_return_parameter_is_allowlisted_not_an_open_redirect(self):
        for destination in ('https://example.com/', '//example.com/', '/admin/'):
            with self.subTest(destination=destination):
                response = self.client.post(self.url, {'return_to':destination,'avatar_action':'delete'})
                self.assertRedirects(response, reverse('profile', args=[self.owner.username]))
