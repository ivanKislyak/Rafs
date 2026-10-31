import json
from html import escape
from io import BytesIO
from tempfile import TemporaryDirectory
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone
from django.utils import translation
from django.utils.formats import get_format
from django.conf import settings
from PIL import Image
from rest_framework.test import APIClient
from django.core.cache import cache

from accounts.models import Achievement, SearchHistory, User
from movies.models import Movie, Review, ReviewReply, WatchStatus

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


class ProfilePageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="profile_owner",
            email="owner@example.com",
            password="password123",
            user_frames=1600,
        )
        self.visitor = User.objects.create_user(
            username="profile_visitor",
            email="visitor@example.com",
            password="password123",
        )
        self.profile_url = reverse(
            "profile",
            kwargs={"username": self.owner.username},
        )

    def test_profile_uses_root_url_and_header_links_to_it(self):
        self.assertEqual(self.profile_url, f"/@{self.owner.username}/")
        self.assertEqual(resolve(self.profile_url).view_name, "profile")
        self.client.force_login(self.owner)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, f'href="{self.profile_url}"')

    def test_removed_profile_urls_are_not_available(self):
        for url in [
            f"/{self.owner.username}/",
            f"/accounts/profile/{self.owner.username}/",
            "/accounts/profile/",
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_profile_is_public_but_private_controls_and_email_are_hidden(self):
        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.owner.username)
        self.assertNotContains(response, self.owner.email)
        self.assertNotContains(response, "Change avatar")

        self.client.force_login(self.visitor)
        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.owner.email)
        self.assertNotContains(response, "Change avatar")

    def test_owner_sees_email_and_profile_controls(self):
        self.client.force_login(self.owner)

        response = self.client.get(self.profile_url)

        self.assertContains(response, self.owner.email)
        self.assertContains(response, "Change avatar")
        self.assertNotContains(response, "Apply for moderation")
        self.assertNotContains(response, "View applications")
        self.assertTrue(response.context["is_owner"])

    def test_profile_statistics_are_correct(self):
        first_movie = Movie.objects.create(name="First movie", year=2001)
        second_movie = Movie.objects.create(name="Second movie", year=2002)
        first_review = Review.objects.create(
            user=self.owner,
            movie=first_movie,
            rating=8,
        )
        Review.objects.create(
            user=self.owner,
            movie=second_movie,
            rating=7,
        )
        ReviewReply.objects.create(
            review=first_review,
            user=self.owner,
            text="First reply",
        )
        ReviewReply.objects.create(
            review=first_review,
            user=self.owner,
            text="Second reply",
        )
        WatchStatus.objects.create(
            user=self.owner,
            movie=first_movie,
            status=WatchStatus.StatusChoice.VIEWED,
        )
        WatchStatus.objects.create(
            user=self.owner,
            movie=second_movie,
            status=WatchStatus.StatusChoice.WILL_WATCH,
        )

        response = self.client.get(self.profile_url)

        self.assertEqual(response.context["profile_user"].review_count, 2)
        self.assertEqual(response.context["profile_user"].reply_count, 2)
        status_counts = {
            item["value"]: item["count"]
            for item in response.context["watch_statuses"]
        }
        self.assertEqual(status_counts[WatchStatus.StatusChoice.VIEWED], 1)
        self.assertEqual(status_counts[WatchStatus.StatusChoice.WILL_WATCH], 1)
        self.assertEqual(status_counts[WatchStatus.StatusChoice.DROPPED], 0)

    def test_profile_uses_bounded_number_of_queries(self):
        achievement = Achievement.objects.create(
            name="First step",
            description="A test achievement",
        )
        self.owner.achievement.add(achievement)

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 3)

    def test_public_library_is_visible_but_controls_are_owner_only(self):
        movie = Movie.objects.create(name="Public library movie", year=2023)
        WatchStatus.objects.create(
            user=self.owner,
            movie=movie,
            status=WatchStatus.StatusChoice.WATCHING,
        )

        anonymous_response = self.client.get(self.profile_url)
        self.assertContains(anonymous_response, movie.name)
        self.assertNotContains(anonymous_response, "data-library-remove")

        self.client.force_login(self.visitor)
        visitor_response = self.client.get(self.profile_url)
        self.assertContains(visitor_response, movie.name)
        self.assertNotContains(visitor_response, "data-library-remove")

        self.client.force_login(self.owner)
        owner_response = self.client.get(self.profile_url)
        self.assertContains(owner_response, movie.name)
        self.assertContains(owner_response, "data-library-remove")

    def test_empty_watch_categories_render_without_error(self):
        response = self.client.get(self.profile_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "There are no movies in this section yet")
        self.assertEqual(len(response.context["watch_statuses"]), 6)

    def test_library_query_count_does_not_grow_with_movie_count(self):
        first_movie = Movie.objects.create(name="Query movie 0", year=2020)
        WatchStatus.objects.create(
            user=self.owner,
            movie=first_movie,
            status=WatchStatus.StatusChoice.VIEWED,
        )

        with CaptureQueriesContext(connection) as initial_queries:
            initial_response = self.client.get(self.profile_url)
        self.assertEqual(initial_response.status_code, 200)

        for index in range(1, 7):
            movie = Movie.objects.create(name=f"Query movie {index}", year=2020 + index)
            WatchStatus.objects.create(
                user=self.owner,
                movie=movie,
                status=WatchStatus.StatusChoice.WILL_WATCH,
            )

        with CaptureQueriesContext(connection) as populated_queries:
            populated_response = self.client.get(self.profile_url)
        self.assertEqual(populated_response.status_code, 200)
        self.assertLessEqual(len(populated_queries), len(initial_queries) + 1)

    def test_deleted_users_profile_is_not_public(self):
        self.owner.delete()
        self.assertEqual(self.client.get(self.profile_url).status_code, 404)


class ProfileLibraryLocalizationTests(TestCase):
    titles = {
        "en": 'English "title" & <work>',
        "ru": 'Очень длинное русское название "произведения" & <детали> ' * 5,
        "uk": "Українська назва твору",
        "kk": "Туындының қазақша атауы",
        "es": "Título de la obra",
        "de": "Deutscher Werktitel",
    }

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="localized-library", email="library@example.com")
        cls.movie = Movie.objects.create(name="Base English name", year=2024)
        for language, title in cls.titles.items():
            cls.movie.set_current_language(language)
            cls.movie.wikidata_name = title
            cls.movie.save()
        WatchStatus.objects.create(user=cls.owner, movie=cls.movie, status=WatchStatus.StatusChoice.VIEWED)

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
    def profile(self, language):
        return self.client.get(
            reverse("profile", args=[self.owner.username]), HTTP_ACCEPT_LANGUAGE=language,
        )

    def assert_title(self, response, title):
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-movie-name="{escape(title)}"')
        self.assertContains(response, f'aria-label="{escape(title)}"')
        self.assertContains(response, f'alt="{escape(title)}"')
        self.assertContains(response, f'title="{escape(title)}"')
        self.assertContains(response, f'>{escape(title)}</a>')

    def test_active_language_localizes_titles_attributes_and_all_ui_states(self):
        self.client.force_login(self.owner)
        for language, _ in settings.LANGUAGES:
            with self.subTest(language=language), translation.override(language):
                response = self.profile(language)
                self.assert_title(response, self.titles[language].strip())
                for attribute, message in [
                    ("data-update-loading", "Loading..."),
                    ("data-update-restored", "Restored to list"),
                    ("data-update-error", "Unable to update the list"),
                    ("aria-label", "Remove from list"),
                ]:
                    self.assertContains(response, f'{attribute}="{escape(translation.gettext(message))}"')
                for message in [
                    "Library", "Watch statuses", "Undo", "Removed from list",
                    "There are no movies in this section yet", "Cancel", "Confirm",
                ]:
                    self.assertContains(response, translation.gettext(message))
                for _, label in WatchStatus.StatusChoice.choices:
                    self.assertContains(response, escape(str(label)))
                self.assertContains(response, f'data-number-grouping="{get_format("NUMBER_GROUPING")}"')
                self.assertContains(response, f'data-thousand-separator="{escape(get_format("THOUSAND_SEPARATOR"))}"')

    def test_cookie_language_takes_precedence_over_accept_language(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ru"
        self.assert_title(self.profile("en"), self.titles["ru"].strip())

    def test_missing_or_empty_translation_uses_configured_fallback_then_base_name(self):
        english_only = Movie.objects.create(name="", wikidata_id="CHECK_EN")
        english_only.set_current_language("en")
        english_only.wikidata_name = "English fallback"
        english_only.save()
        english_only.set_current_language("ru")
        english_only.wikidata_name = ""
        english_only.wikidata_description = "Описание без переведённого названия"
        english_only.save()
        russian_only = Movie.objects.create(name="", wikidata_id="CHECK_RU")
        russian_only.set_current_language("ru")
        russian_only.wikidata_name = "Русский fallback"
        russian_only.save()
        legacy = Movie.objects.create(name="Legacy base title")
        for movie in [english_only, russian_only, legacy]:
            WatchStatus.objects.create(user=self.owner, movie=movie, status=WatchStatus.StatusChoice.VIEWED)
        response = self.profile("es")
        for title in ["English fallback", "Русский fallback", "Legacy base title"]:
            self.assert_title(response, title)
        self.assert_title(self.profile("ru"), "English fallback")

    def test_missing_all_title_data_has_localized_placeholder(self):
        unnamed = Movie.objects.create(name="")
        WatchStatus.objects.create(user=self.owner, movie=unnamed, status=WatchStatus.StatusChoice.VIEWED)
        for language, _ in settings.LANGUAGES:
            with self.subTest(language=language), translation.override(language):
                self.assert_title(self.profile(language), translation.gettext("Untitled"))

    def test_translation_query_count_does_not_grow_with_library(self):
        with CaptureQueriesContext(connection) as initial:
            self.assertEqual(self.profile("ru").status_code, 200)
        for i in range(15):
            movie = Movie.objects.create(name=f"Base movie {i}")
            for language in ["en", "ru"]:
                movie.set_current_language(language)
                movie.wikidata_name = f"Translation {language} {i}"
                movie.save()
            WatchStatus.objects.create(user=self.owner, movie=movie, status=WatchStatus.StatusChoice.VIEWED)
        with CaptureQueriesContext(connection) as populated:
            self.assertEqual(self.profile("ru").status_code, 200)
        self.assertEqual(len(populated), len(initial))
        table = Movie._parler_meta.root_model._meta.db_table
        self.assertEqual(sum(f'"{table}"' in q["sql"] for q in populated), 1)


class AvatarUpdateTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()
        self.user = User.objects.create_user(
            username="avatar_owner",
            email="avatar@example.com",
            password="password123",
        )
        self.url = reverse("accounts:update-avatar")

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()

    @staticmethod
    def make_bmp_upload():
        image_bytes = BytesIO()
        Image.new("RGB", (24, 18), color=(120, 20, 20)).save(image_bytes, format="BMP")
        return SimpleUploadedFile(
            "avatar.bmp",
            image_bytes.getvalue(),
            content_type="image/bmp",
        )

    def test_avatar_update_requires_authentication(self):
        response = self.client.post(self.url, {"avatar_image": self.make_bmp_upload()})

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_owner_can_upload_normalized_avatar_and_remove_it(self):
        self.client.force_login(self.user)

        response = self.client.post(
            self.url,
            {"avatar_image": self.make_bmp_upload()},
        )

        self.assertRedirects(
            response,
            reverse("profile", kwargs={"username": self.user.username}),
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar_image.name.endswith(".png"))
        self.assertTrue(self.user.avatar_image.storage.exists(self.user.avatar_image.name))

        response = self.client.post(self.url, {"avatar_action": "delete"})

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar_image)


class MeProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="profile-editor", email="editor@example.com",
            about='Hello <script>alert("x")</script> & friends\nSecond line',
            sex="M", bd_date="2000-02-29",
        )
        cls.other = User.objects.create_user(username="another-profile", email="other@example.com")

    def setUp(self):
        self.client = APIClient()
        self.client.force_login(self.owner)
        self.url = reverse("accounts:me")
        self.profile_url = reverse("profile", args=[self.owner.username])

    def test_get_returns_only_current_users_profile_and_contract(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "id": self.owner.pk, "username": self.owner.username,
            "about": self.owner.about, "sex": "M", "bd_date": "2000-02-29",
        })

    def test_partial_updates_preserve_fields_not_sent(self):
        expected = self.client.get(self.url).json()
        for field, value in [("about", "New biography\n<not HTML>"), ("sex", "O"), ("bd_date", "1999-12-31")]:
            with self.subTest(field=field):
                response = self.client.patch(self.url, {field: value}, format="json")
                expected[field] = value
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), expected)
                self.owner.refresh_from_db()
                self.assertEqual(str(getattr(self.owner, field)), value)

    def test_fields_can_be_cleared(self):
        response = self.client.patch(self.url, {"about": "", "sex": "", "bd_date": None}, format="json")
        self.assertEqual(response.status_code, 200)
        for field, value in [("about", ""), ("sex", ""), ("bd_date", None)]:
            self.assertEqual(response.json()[field], value)
        self.owner.refresh_from_db()
        self.assertEqual((self.owner.about, self.owner.sex, self.owner.bd_date), ("", "", None))

    def test_invalid_input_returns_field_errors_and_preserves_profile(self):
        original = self.client.get(self.url).json()
        for field, value in [("about", "x" * 1001), ("sex", "invalid"), ("bd_date", "2000-02-30")]:
            with self.subTest(field=field):
                response = self.client.patch(self.url, {field: value}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json())
                self.assertEqual(self.client.get(self.url).json(), original)

    def test_identity_is_read_only_and_other_user_is_unchanged(self):
        response = self.client.patch(self.url, {
            "id": self.other.pk, "username": self.other.username, "about": "Updated",
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.owner.pk)
        self.assertEqual(response.json()["username"], self.owner.username)
        self.other.refresh_from_db()
        self.assertEqual(self.other.about, "")

    def test_anonymous_cannot_read_or_patch_me(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.patch(self.url, {"about": "No"}, format="json").status_code, 403)

    def test_session_patch_requires_csrf_from_profile_form(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.patch(self.url, {"about": "No"}, format="json").status_code, 403)
        response = client.get(self.profile_url)
        from html.parser import HTMLParser

        class Tokens(HTMLParser):
            token = None

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "input" and attrs.get("name") == "csrfmiddlewaretoken":
                    self.token = attrs["value"]

        parser = Tokens()
        parser.feed(response.content.decode())
        self.assertTrue(parser.token)
        response = client.patch(self.url, {"about": "CSRF checked"}, format="json", HTTP_X_CSRFTOKEN=parser.token)
        self.assertEqual(response.status_code, 200)

    def test_owner_editor_choices_and_escaped_public_about_without_private_fields(self):
        response = self.client.get(self.profile_url)
        self.assertContains(response, f'data-api-url="{self.url}"')
        self.assertContains(response, 'accounts/js/profile-edit.js')
        self.assertContains(response, 'data-avatar-editor')
        self.assertContains(response, 'data-profile-library')
        for value, label in User.SexChoice.choices:
            self.assertContains(response, f'<option value="{value}">{label}</option>')
        for authenticated in [True, False]:
            if authenticated:
                self.client.force_login(self.other)
            else:
                self.client.logout()
            response = self.client.get(self.profile_url)
            self.assertContains(response, escape(self.owner.about))
            self.assertNotContains(response, self.owner.about)
            for private in ['data-profile-editor', 'data-profile-edit-open', 'accounts/js/profile-edit.js',
                            'name="sex"', 'name="bd_date"', self.owner.email, self.url]:
                self.assertNotContains(response, private)

    def test_editor_strings_are_localized_on_all_supported_languages(self):
        messages = [
            "Edit profile", "About me", "Sex", "Not specified", "Date of birth", "Save", "Cancel",
            "Loading...", "Saving...", "Try again", "Unable to load your profile",
            "Unable to save your profile", "Access denied. Sign in again and reload the page", "Profile saved",
        ]
        for language, _ in settings.LANGUAGES:
            with self.subTest(language=language), translation.override(language):
                response = self.client.get(self.profile_url, HTTP_ACCEPT_LANGUAGE=language)
                self.assertEqual(response.status_code, 200)
                for message in messages:
                    translated = translation.gettext(message)
                    self.assertContains(response, escape(translated))
                    if language != "en":
                        self.assertNotEqual(translated, message)
                for _, label in User.SexChoice.choices:
                    self.assertContains(response, escape(str(label)))


class SearchHistoryAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="history-owner", email="history-owner@example.com",
        )
        cls.other = User.objects.create_user(
            username="history-other", email="history-other@example.com",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.url = reverse("accounts:searchhistory-list")

    def test_invalid_queries_return_400_without_creating_history(self):
        invalid_payloads = [
            {}, {"query": ""}, {"query": " \t\n "}, {"query": "x" * 201},
            {"query": None}, {"query": []}, {"query": {}},
            {"query": True}, {"query": 123}, {"query": 1.5},
            [], [{"query": "movie"}], "movie", None,
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                # Encode explicitly so JSON null and scalar bodies reach the API unchanged.
                response = self.client.post(
                    self.url, data=json.dumps(payload), content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(SearchHistory.objects.count(), 0)

    def test_repeated_search_updates_existing_entry_and_orders_it_first(self):
        first = self.client.post(self.url, {"query": "  first film  "}, format="json")
        self.assertEqual(first.status_code, 201)
        entry = SearchHistory.objects.get(pk=first.json()["id"])
        self.assertEqual(entry.query, "first film")
        old_time = timezone.now() - timedelta(days=1)
        SearchHistory.objects.filter(pk=entry.pk).update(updated_at=old_time)
        later = SearchHistory.objects.create(user=self.owner, query="second film")

        repeated = self.client.post(self.url, {"query": "first film"}, format="json")

        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()["id"], entry.pk)
        self.assertEqual(SearchHistory.objects.filter(user=self.owner).count(), 2)
        entry.refresh_from_db()
        self.assertGreater(entry.updated_at, later.updated_at)
        listing = self.client.get(self.url)
        self.assertEqual([item["id"] for item in listing.json()["results"]], [entry.pk, later.pk])

    def test_client_cannot_assign_another_owner(self):
        other_entry = SearchHistory.objects.create(user=self.other, query="same film")
        old_time = timezone.now() - timedelta(days=1)
        SearchHistory.objects.filter(pk=other_entry.pk).update(updated_at=old_time)

        response = self.client.post(
            self.url, {"query": "same film", "user": self.other.pk}, format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["user"], self.owner.pk)
        self.assertTrue(SearchHistory.objects.filter(user=self.owner, query="same film").exists())
        other_entry.refresh_from_db()
        self.assertEqual(other_entry.user_id, self.other.pk)
        self.assertEqual(other_entry.updated_at, old_time)

    def test_list_retrieve_and_delete_are_limited_to_current_user(self):
        own_entry = SearchHistory.objects.create(user=self.owner, query="own film")
        other_entry = SearchHistory.objects.create(user=self.other, query="private film")
        own_url = reverse("accounts:searchhistory-detail", args=[own_entry.pk])
        other_url = reverse("accounts:searchhistory-detail", args=[other_entry.pk])

        self.assertEqual([item["id"] for item in self.client.get(self.url).json()["results"]], [own_entry.pk])
        self.assertEqual(self.client.get(own_url).status_code, 200)
        self.assertEqual(self.client.get(other_url).status_code, 404)
        self.assertEqual(self.client.delete(other_url).status_code, 404)
        self.assertTrue(SearchHistory.objects.filter(pk=other_entry.pk).exists())
        self.assertEqual(self.client.delete(own_url).status_code, 204)
        self.assertFalse(SearchHistory.objects.filter(pk=own_entry.pk).exists())

    def test_anonymous_requests_are_rejected(self):
        self.client.force_authenticate(user=None)
        entry = SearchHistory.objects.create(user=self.owner, query="private film")
        detail_url = reverse("accounts:searchhistory-detail", args=[entry.pk])
        for method, url, kwargs in [
            ("get", self.url, {}),
            ("get", detail_url, {}),
            ("post", self.url, {"data": {"query": "film"}, "format": "json"}),
            ("delete", detail_url, {}),
        ]:
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url, **kwargs).status_code, 403)
        self.assertEqual(SearchHistory.objects.count(), 1)

    def test_session_authenticated_posts_require_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.url, {"query": "film"}).status_code, 403)
        client.get(reverse("core:home"))
        response = client.post(
            self.url, {"query": "film"}, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )
        self.assertEqual(response.status_code, 201)
