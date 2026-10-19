import json
from io import BytesIO
from tempfile import TemporaryDirectory
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

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
        self.assertEqual([item["id"] for item in listing.json()], [entry.pk, later.pk])

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

        self.assertEqual([item["id"] for item in self.client.get(self.url).json()], [own_entry.pk])
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
