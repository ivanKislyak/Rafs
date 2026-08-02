from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .forms import ReviewForm
from .models import Movie, Review


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
