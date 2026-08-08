import json

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from .forms import ReviewForm
from .models import Movie, Review, ReviewVote


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
