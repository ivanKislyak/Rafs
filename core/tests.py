from django.test import TestCase
from .views import HomePageView
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

    def test_code_200(self):
        response = self.client.get(reverse("core:home"))
        self.assertTemplateUsed(response, "core/home.html")

    def test_top_movies(self):
        response = self.client.get(reverse("core:home"))
        top_movies = list(
            response.context["top_movies"].values_list("name", flat=True)
        )

        self.assertEqual(top_movies, ["Scary movie 6", "Great mile", "Forrest Gump", "Titan", "10 lives"])

    def test_len_movies(self):
        response = self.client.get(reverse("core:home"))
        len_movies = len(response.context["top_movies"])

        self.assertEqual(len_movies, 5)
