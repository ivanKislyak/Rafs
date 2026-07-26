from django.test import TestCase
from movies.models import Movie
from django.urls import reverse

class TestHomePageView(TestCase):
    @classmethod
    def setUpTestData(cls):
        Movie.objects.create(name="Forrest Gump", rate=7.3, year=1994)
        Movie.objects.create(name="Great mile", rate=9, year=1999)
        Movie.objects.create(name="Scary movie 6", rate=10, year=2026)
        Movie.objects.create(name="10 lives", rate=3, year=2024)
        Movie.objects.create(name="Titan", rate=4.3, year=2021)
        Movie.objects.create(name="One Piece", rate=7.8, year=1997)

    def setUp(self):
        self.url = reverse("core:home")
        self.response = self.client.get(self.url)

    def test_code_200(self):
        self.assertTemplateUsed(self.response, "core/home.html")
        self.assertEqual(self.response.status_code, 200)

    def test_top_movies(self):
        top_movies = list(self.response.context["top_movies"].values_list("name", flat=True))
        len_movies = len(top_movies)
        
        self.assertEqual(top_movies, ["Scary movie 6", "Great mile", "One Piece", "Forrest Gump", "Titan"])
        self.assertEqual(len_movies, 5)

    def test_no_rate_movie(self):
        Movie.objects.create(name="Once upon a time on None Movie", rate=None, year=1997)
        response = self.client.get(self.url)
        top_movies = list(
            response.context["top_movies"].values_list("name", flat=True)
        )

        self.assertNotIn("Once upon a time on None Movie", top_movies)
