from django.contrib.auth import get_user_model
from django.test import TestCase
from movies.models import Movie, Review
from django.urls import reverse

class TestHomePageView(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = get_user_model().objects.create_user(
            username="home-reviewer",
            password="test-password",
        )
        movie_ratings = (
            ("Forrest Gump", 7.3, 1994),
            ("Great mile", 9, 1999),
            ("Scary movie 6", 10, 2026),
            ("10 lives", 3, 2024),
            ("Titan", 4.3, 2021),
            ("One Piece", 7.8, 1997),
        )

        for name, rating, year in movie_ratings:
            movie = Movie.objects.create(name=name, rate=10 - rating, year=year)
            Review.objects.create(user=user, movie=movie, rating=rating)

    def setUp(self):
        self.url = reverse("core:home")
        self.response = self.client.get(self.url)

    def test_code_200(self):
        self.assertTemplateUsed(self.response, "core/home.html")
        self.assertEqual(self.response.status_code, 200)

    def test_top_movies(self):
        top_movies = list(self.response.context["top_movies"].values_list("name", flat=True))
        len_movies = len(top_movies)
        
        self.assertEqual(top_movies, ["Scary movie 6", "Great mile", "One Piece", "Forrest Gump", "Titan", "10 lives"])
        self.assertEqual(len_movies, 6)

    def test_movie_without_reviews_is_not_in_top(self):
        Movie.objects.create(name="Movie without reviews", rate=10, year=1997)
        response = self.client.get(self.url)
        top_movies = list(
            response.context["top_movies"].values_list("name", flat=True)
        )

        self.assertNotIn("Movie without reviews", top_movies)
