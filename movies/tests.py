import json

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .forms import ReviewForm
from .models import Movie, Review, ReviewReply, ReviewVote, WatchStatus


class ReviewFormTests(SimpleTestCase):
    def test_review_form_contains_expected_fields(self):
        form = ReviewForm()

        self.assertIn("rating", form.fields)
        self.assertIn("text", form.fields)
        self.assertIn("contains_spoiler", form.fields)


class CatalogRatingFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = get_user_model().objects.create_user(
            username="catalog-reviewer",
            password="test-password",
        )
        high_review_rating = Movie.objects.create(
            name="High review rating",
            rate=1,
            year=2020,
        )
        low_review_rating = Movie.objects.create(
            name="Low review rating",
            rate=10,
            year=2021,
        )
        Review.objects.create(user=user, movie=high_review_rating, rating=9)
        Review.objects.create(user=user, movie=low_review_rating, rating=3)

    def test_min_rating_uses_review_average(self):
        response = self.client.get(reverse("movies:catalog"), {"min_rating": 8})
        movies = list(response.context["movie"].values_list("name", flat=True))

        self.assertIn("High review rating", movies)
        self.assertNotIn("Low review rating", movies)


class ReviewFramesRewardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="reward-reviewer",
            password="test-password",
        )
        cls.movie = Movie.objects.create(name="Reward test movie", year=2024)

    def setUp(self):
        self.client.force_login(self.user)

    def submit_review(self, text):
        return self.client.post(
            reverse("movies:review_form", args=[self.movie.id]),
            data={"rating": "8.0", "text": text},
            follow=True,
        )

    def test_new_review_rewards_frames_and_displays_notification(self):
        response = self.submit_review("First review")

        self.user.refresh_from_db()
        self.assertEqual(self.user.user_frames, 101)
        self.assertContains(response, "+100 Кадров")
        self.assertContains(response, "frames-reward")

    def test_editing_review_does_not_reward_frames_again(self):
        self.submit_review("First review")
        response = self.submit_review("Updated review")

        self.user.refresh_from_db()
        self.assertEqual(self.user.user_frames, 101)
        self.assertNotContains(response, "+100 Кадров")


class ReviewVoteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        author = get_user_model().objects.create_user(
            username="review-author",
            email="author@example.com",
        )
        cls.voter = get_user_model().objects.create_user(
            username="review-voter",
            email="voter@example.com",
        )
        movie = Movie.objects.create(name="Vote test movie", year=2020)
        cls.review = Review.objects.create(
            user=author,
            movie=movie,
            rating=8,
            text="Test review",
        )

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.voter)
        self.client.get(reverse("movies:detail", args=[self.review.movie_id]))
        self.csrf_token = self.client.cookies["csrftoken"].value

    def send_vote(self, value):
        return self.client.post(
            reverse("movies:vote_review"),
            data=json.dumps({"review_id": self.review.id, "vote_value": value}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

    def test_like_toggle_and_dislike_switch_are_saved(self):
        like_response = self.send_vote(1)
        self.assertEqual(like_response.status_code, 200)
        self.assertEqual(like_response.json()["likes"], 1)
        self.assertTrue(
            ReviewVote.objects.filter(
                review=self.review,
                user=self.voter,
                value=ReviewVote.VoteChoice.LIKE,
            ).exists()
        )

        remove_response = self.send_vote(1)
        self.assertEqual(remove_response.json()["user_vote"], 0)
        self.assertFalse(
            ReviewVote.objects.filter(review=self.review, user=self.voter).exists()
        )

        dislike_response = self.send_vote(-1)
        self.assertEqual(dislike_response.json()["dislikes"], 1)
        self.assertTrue(
            ReviewVote.objects.filter(
                review=self.review,
                user=self.voter,
                value=ReviewVote.VoteChoice.DISLIKE,
            ).exists()
        )

        detail_response = self.client.get(
            reverse("movies:detail", args=[self.review.movie_id])
        )
        displayed_review = detail_response.context["reviews"][0]
        self.assertEqual(displayed_review.dislike_count, 1)
        self.assertEqual(displayed_review.user_vote, ReviewVote.VoteChoice.DISLIKE)


class ReviewReplyDisplayTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.first_author = get_user_model().objects.create_user(
            username="first-author",
            email="first-author@example.com",
        )
        cls.second_author = get_user_model().objects.create_user(
            username="second-author",
            email="second-author@example.com",
        )
        cls.reply_author = get_user_model().objects.create_user(
            username="reply-author",
            email="reply-author@example.com",
        )
        cls.movie = Movie.objects.create(name="Replies movie", year=2025)
        cls.first_review = Review.objects.create(
            user=cls.first_author,
            movie=cls.movie,
            rating=8,
            text="First review",
        )
        cls.second_review = Review.objects.create(
            user=cls.second_author,
            movie=cls.movie,
            rating=7,
            text="Second review",
        )
        cls.first_reply = ReviewReply.objects.create(
            review=cls.first_review,
            user=cls.reply_author,
            text="First line\nSecond line",
        )
        cls.second_reply = ReviewReply.objects.create(
            review=cls.second_review,
            user=cls.first_author,
            text="Only for the second review",
        )
        cls.detail_url = reverse("movies:detail", args=[cls.movie.id])

    def test_replies_belong_to_their_own_review(self):
        response = self.client.get(self.detail_url)
        reviews = {review.id: review for review in response.context["reviews"]}

        self.assertEqual(
            [reply.id for reply in reviews[self.first_review.id].loaded_replies],
            [self.first_reply.id],
        )
        self.assertEqual(
            [reply.id for reply in reviews[self.second_review.id].loaded_replies],
            [self.second_reply.id],
        )

    def test_review_and_reply_authors_link_to_public_profiles(self):
        response = self.client.get(self.detail_url)

        self.assertContains(
            response,
            f'href="{reverse("accounts:profile", kwargs={"username": self.first_author.username})}"',
        )
        self.assertContains(
            response,
            f'href="{reverse("accounts:profile", kwargs={"username": self.reply_author.username})}"',
        )

    def test_review_without_replies_has_no_reply_toggle(self):
        ReviewReply.objects.all().delete()

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<button class="review-replies-toggle"')

    def test_reply_prefetch_query_count_does_not_grow_with_reply_count(self):
        with CaptureQueriesContext(connection) as initial_queries:
            initial_response = self.client.get(self.detail_url)
        self.assertEqual(initial_response.status_code, 200)

        for index in range(6):
            author = get_user_model().objects.create_user(
                username=f"extra-reply-author-{index}",
                email=f"extra-reply-{index}@example.com",
            )
            ReviewReply.objects.create(
                review=self.first_review,
                user=author,
                text=f"Extra reply {index}",
            )

        with CaptureQueriesContext(connection) as populated_queries:
            populated_response = self.client.get(self.detail_url)
        self.assertEqual(populated_response.status_code, 200)
        self.assertLessEqual(len(populated_queries), len(initial_queries) + 1)

    def test_reply_post_returns_to_open_reply_thread(self):
        self.client.force_login(self.reply_author)

        response = self.client.post(
            reverse("movies:reply_review", args=[self.first_review.id]),
            {"text": "A newly posted reply"},
        )

        expected_url = (
            f"{self.detail_url}?replies={self.first_review.id}"
            f"#review-{self.first_review.id}"
        )
        self.assertRedirects(response, expected_url)

        detail_response = self.client.get(
            self.detail_url,
            {"replies": self.first_review.id},
        )
        self.assertContains(detail_response, 'aria-expanded="true"')
        self.assertContains(detail_response, f'id="review-replies-{self.first_review.id}"')
        self.assertContains(detail_response, "A newly posted reply")


class WatchStatusEndpointTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="library-owner",
            email="library-owner@example.com",
        )
        self.other_user = get_user_model().objects.create_user(
            username="other-library-owner",
            email="other-library-owner@example.com",
        )
        self.movie = Movie.objects.create(name="Library movie", year=2024)
        self.url = reverse("movies:set_movie_status")

    def post_status(self, user, status, **extra_payload):
        self.client.force_login(user)
        payload = {
            "movie_id": self.movie.id,
            "status": status,
            **extra_payload,
        }
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_repeating_status_removes_and_then_restores_it(self):
        WatchStatus.objects.create(
            user=self.owner,
            movie=self.movie,
            status=WatchStatus.StatusChoice.VIEWED,
        )

        remove_response = self.post_status(
            self.owner,
            WatchStatus.StatusChoice.VIEWED,
        )
        self.assertEqual(remove_response.status_code, 200)
        self.assertIsNone(remove_response.json()["status"])
        self.assertFalse(
            WatchStatus.objects.filter(user=self.owner, movie=self.movie).exists()
        )

        restore_response = self.post_status(
            self.owner,
            WatchStatus.StatusChoice.VIEWED,
        )
        self.assertEqual(restore_response.status_code, 200)
        self.assertEqual(
            restore_response.json()["status"],
            WatchStatus.StatusChoice.VIEWED,
        )
        self.assertTrue(
            WatchStatus.objects.filter(
                user=self.owner,
                movie=self.movie,
                status=WatchStatus.StatusChoice.VIEWED,
            ).exists()
        )

    def test_payload_cannot_change_another_users_status(self):
        other_status = WatchStatus.objects.create(
            user=self.other_user,
            movie=self.movie,
            status=WatchStatus.StatusChoice.DROPPED,
        )

        response = self.post_status(
            self.owner,
            WatchStatus.StatusChoice.VIEWED,
            user_id=self.other_user.id,
            username=self.other_user.username,
        )

        self.assertEqual(response.status_code, 200)
        other_status.refresh_from_db()
        self.assertEqual(other_status.status, WatchStatus.StatusChoice.DROPPED)
        self.assertTrue(
            WatchStatus.objects.filter(
                user=self.owner,
                movie=self.movie,
                status=WatchStatus.StatusChoice.VIEWED,
            ).exists()
        )


class ReviewDeletionPermissionTests(TestCase):
    def setUp(self):
        self.review_author = get_user_model().objects.create_user(
            username="delete-review-author",
            email="delete-review-author@example.com",
        )
        self.reply_author = get_user_model().objects.create_user(
            username="delete-reply-author",
            email="delete-reply-author@example.com",
        )
        self.outsider = get_user_model().objects.create_user(
            username="delete-outsider",
            email="delete-outsider@example.com",
        )
        self.superuser = get_user_model().objects.create_superuser(
            username="delete-admin",
            email="delete-admin@example.com",
            password="password123",
        )
        self.movie = Movie.objects.create(name="Deletion movie", year=2025)
        self.review = Review.objects.create(
            user=self.review_author,
            movie=self.movie,
            rating=8,
            text="Review to delete",
        )
        self.reply = ReviewReply.objects.create(
            review=self.review,
            user=self.reply_author,
            text="Reply to delete",
        )

    def test_reply_author_can_delete_own_reply(self):
        self.client.force_login(self.reply_author)
        detail_response = self.client.get(
            reverse("movies:detail", args=[self.movie.id])
        )
        delete_url = reverse("movies:delete_reply", args=[self.reply.id])
        self.assertContains(detail_response, f'action="{delete_url}"')

        response = self.client.post(delete_url)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ReviewReply.objects.filter(id=self.reply.id).exists())

    def test_other_user_cannot_delete_review_or_reply(self):
        self.client.force_login(self.outsider)

        reply_response = self.client.post(
            reverse("movies:delete_reply", args=[self.reply.id])
        )
        review_response = self.client.post(
            reverse("movies:delete_review", args=[self.review.id])
        )

        self.assertEqual(reply_response.status_code, 403)
        self.assertEqual(review_response.status_code, 403)
        self.assertTrue(ReviewReply.objects.filter(id=self.reply.id).exists())
        self.assertTrue(Review.objects.filter(id=self.review.id).exists())

    def test_superuser_can_delete_any_reply_and_review(self):
        self.client.force_login(self.superuser)
        detail_response = self.client.get(
            reverse("movies:detail", args=[self.movie.id])
        )
        reply_delete_url = reverse("movies:delete_reply", args=[self.reply.id])
        review_delete_url = reverse("movies:delete_review", args=[self.review.id])
        self.assertContains(detail_response, f'action="{reply_delete_url}"')
        self.assertContains(detail_response, f'action="{review_delete_url}"')

        reply_response = self.client.post(reply_delete_url)
        review_response = self.client.post(review_delete_url)

        self.assertEqual(reply_response.status_code, 302)
        self.assertEqual(review_response.status_code, 302)
        self.assertFalse(ReviewReply.objects.filter(id=self.reply.id).exists())
        self.assertFalse(Review.objects.filter(id=self.review.id).exists())
