from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from movies.models import Movie


class StaticSitemap(Sitemap):
    protocol = "https"

    def items(self):
        return ["core:home", "core:about", "movies:catalog"]

    def location(self, item):
        return reverse(item)


class MovieSitemap(Sitemap):
    protocol = "https"

    def items(self):
        return Movie.objects.only("id").order_by("id")

    def location(self, movie):
        return reverse("movies:detail", kwargs={"movie_id": movie.pk})