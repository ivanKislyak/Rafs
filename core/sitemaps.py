from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from movies.models import Movie
from core.seo import PUBLIC_DOMAIN


class PublicSitemap(Sitemap):
    protocol = "https"

    def get_domain(self, site=None):
        # Django's RequestSite otherwise uses the requesting host (e.g. localhost).
        return PUBLIC_DOMAIN


class StaticSitemap(PublicSitemap):
    def items(self):
        return ["core:home", "core:about", "movies:catalog",
                "movies:show_reviews", "core:community_guidelines"]

    def location(self, item):
        return reverse(item)


class MovieSitemap(PublicSitemap):
    def items(self):
        return Movie.objects.only("id").order_by("id")

    def location(self, movie):
        return reverse("movies:detail", kwargs={"movie_id": movie.pk})
