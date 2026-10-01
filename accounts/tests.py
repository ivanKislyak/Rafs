from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from PIL import Image

from accounts.models import Achievement, ModerationApplication, User
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
            "accounts:profile",
            kwargs={"username": self.owner.username},
        )

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
        self.assertContains(response, "Apply for moderation")
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
        self.assertContains(response, "There are no movies in this section yet.")
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

    def test_own_profile_shortcut_requires_login_and_redirects_to_username(self):
        shortcut_url = reverse("accounts:own-profile")
        response = self.client.get(shortcut_url)
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={shortcut_url}",
        )

        self.client.force_login(self.owner)
        response = self.client.get(shortcut_url)
        self.assertRedirects(response, self.profile_url)


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
            reverse("accounts:profile", kwargs={"username": self.user.username}),
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar_image.name.endswith(".png"))
        self.assertTrue(self.user.avatar_image.storage.exists(self.user.avatar_image.name))

        response = self.client.post(self.url, {"avatar_action": "delete"})

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar_image)


class ModerationApplicationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="applicant",
            email="applicant@example.com",
            password="password123",
        )
        self.superuser = User.objects.create_superuser(
            username="main_admin",
            email="admin@example.com",
            password="password123",
        )
        self.apply_url = reverse("accounts:moderation-application")
        self.admin_url = reverse("accounts:moderation-applications-admin")

    def test_application_page_requires_login(self):
        response = self.client.get(self.apply_url)

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={self.apply_url}",
        )

    def test_user_can_submit_only_one_application(self):
        self.client.force_login(self.user)

        response = self.client.post(
            self.apply_url,
            {"email": "real-contact@example.com"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ModerationApplication.objects.filter(user=self.user).count(), 1)
        self.assertContains(response, "Application already submitted")

        self.client.post(
            self.apply_url,
            {"email": "different@example.com"},
        )
        application = ModerationApplication.objects.get(user=self.user)
        self.assertEqual(application.email, "real-contact@example.com")
        self.assertEqual(ModerationApplication.objects.filter(user=self.user).count(), 1)

    def test_only_superuser_can_open_application_list(self):
        ModerationApplication.objects.create(
            user=self.user,
            email="real-contact@example.com",
        )
        self.client.force_login(self.user)
        response = self.client.get(self.admin_url)
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.superuser)
        response = self.client.get(self.admin_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)
        self.assertContains(response, "real-contact@example.com")
        self.assertContains(response, "Approve")
        self.assertContains(response, "Reject")
