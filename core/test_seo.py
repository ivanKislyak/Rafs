"""SEO regression checks use the Django test database, not the deployed site."""

import html
import json
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.template import Context
from django.template.loader import get_template
from django.template.loader_tags import BlockNode
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import resolve, reverse
from django.utils import translation

from core.seo import PUBLIC_ORIGIN, WEBSITE, canonical_url, public_image_url
from core.templatetags.seo import website_json_ld
from movies.forms import MovieFilterForm
from movies.models import Movie, Review

LANGUAGES = ("en", "ru", "uk", "kk", "es", "de")
TITLE_BASELINE = json.loads((Path(__file__).parent / "testdata/title_baseline.json").read_text())


class PageHTML(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.meta, self.links, self.anchors, self.schemas = [], [], [], []
        self.title, self.language = "", ""
        self.home_description = ""
        self.in_title, self.in_schema = False, False
        self.in_home_description = False
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            self.language = attrs.get("lang")
        elif tag == "meta":
            self.meta.append(attrs)
        elif tag == "link":
            self.links.append(attrs)
        elif tag == "a":
            self.anchors.append(attrs)
        elif tag == "title":
            self.in_title = True
        elif tag == "script" and attrs.get("type") == "application/ld+json":
            self.in_schema = True
            self.schemas.append("")
        elif tag == "p" and "home-description" in attrs.get("class", "").split():
            self.in_home_description = True

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_schema:
            self.schemas[-1] += data
        if self.in_home_description:
            self.home_description += data

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "script":
            self.in_schema = False
        elif tag == "p":
            self.in_home_description = False

    def values(self, key, value):
        return [meta.get("content", "").strip() for meta in self.meta if meta.get(key) == value]

    @property
    def canonical(self):
        return [link["href"] for link in self.links if link.get("rel") == "canonical"]


class TitleAndSEOHelperTests(SimpleTestCase):
    def test_all_title_blocks_match_pre_change_values_in_six_languages(self):
        # Captured before editing templates/catalogs; covers every title block,
        # including search, profiles, login/register, moderation and review forms.
        samples = {
            "with_year": {"movie": SimpleNamespace(name="SEO Film & <Example>", year=2024),
                          "profile_user": SimpleNamespace(username="seo-user"), "query": "film query"},
            "without_year": {"movie": SimpleNamespace(name="Фильм с длинным названием", year=None),
                             "profile_user": SimpleNamespace(username="длинное_имя_пользователя"), "query": ""},
        }
        for name, languages in TITLE_BASELINE.items():
            template = get_template(name).template
            block = next(node for node in template.nodelist.get_nodes_by_type(BlockNode) if node.name == "title")
            for language, values in languages.items():
                with translation.override(language):
                    for sample, expected in values.items():
                        with self.subTest(template=name, language=language, sample=sample):
                            self.assertEqual(block.render(Context(samples[sample])).strip(), expected)

    def test_json_serialization_escapes_script_delimiters(self):
        value = 'RAFS </script><script>alert("x")</script> & < >'
        with patch.dict(WEBSITE, {"name": value}):
            rendered = str(website_json_ld())
        self.assertEqual(rendered.count("</script>"), 1)
        self.assertEqual(json.loads(PageHTML(rendered).schemas[0])["name"], value)

    def test_canonical_drops_technical_parameters_and_preserves_actual_filters(self):
        request = RequestFactory().get("/movies/", {
            "page": "2", "query": "SEO Film", "year_from": "2000", "year_to": "2025", "min_rating": "7.0",
            "format": "json", "utm_source": "tracking", "email": "private@example.org", "token": "secret",
        })
        request.resolver_match = resolve(request.path)
        context = {"request": request, "filter_form": MovieFilterForm(request.GET),
                   "page_obj": Paginator(range(60), 25).page(2)}
        self.assertEqual(canonical_url(context),
                         "https://rafs.app/movies/?query=SEO+Film&min_rating=7.0&year_from=2000&year_to=2025&page=2")

    def test_image_addresses_are_https_and_reject_unsafe_schemes(self):
        for source, expected in (
            ("/media/poster.jpg", "https://rafs.app/media/poster.jpg"),
            ("http://image.tmdb.org/t/p/w500/poster.jpg", "https://image.tmdb.org/t/p/w500/poster.jpg"),
            ("//image.tmdb.org/t/p/w500/poster.jpg", "https://image.tmdb.org/t/p/w500/poster.jpg"),
        ):
            with self.subTest(source=source):
                self.assertEqual(public_image_url(source), expected)
        for source in ("javascript:alert(1)", "data:image/png;base64,x", "https://user:password@example.org/image.jpg", ""):
            with self.subTest(source=source):
                self.assertTrue(public_image_url(source).startswith("https://rafs.app/static/"))


class PublicSEOTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = get_user_model().objects.create_user(username="seo-user")
        cls.movie = Movie.objects.create(name="SEO Film & <Example>", year=2024,
                                         description="A distinctive plot for this film.")
        movies = [cls.movie] + [Movie.objects.create(name=f"SEO Movie {i:02}", year=2024) for i in range(25)]
        for movie in movies[:11]:
            Review.objects.create(user=cls.author, movie=movie, text="A viewer review", rating=8)

    def get_page(self, name, language="en", **kwargs):
        url_kwargs = kwargs.pop("url_kwargs", {})
        response = self.client.get(reverse(name, kwargs=url_kwargs), HTTP_ACCEPT_LANGUAGE=language, **kwargs)
        self.assertEqual(response.status_code, 200)
        return response, PageHTML(response.content.decode())

    def assert_public_meta(self, page):
        self.assertEqual(len(page.canonical), 1)
        self.assertEqual(len(page.values("name", "description")), 1)
        self.assertTrue(page.values("name", "description")[0])
        for prop in ("og:title", "og:description", "og:url", "og:image"):
            self.assertEqual(len(page.values("property", prop)), 1)
            self.assertTrue(page.values("property", prop)[0])
        self.assertEqual(page.values("property", "og:url"), page.canonical)
        for address in page.canonical + page.values("property", "og:url"):
            self.assertEqual((urlsplit(address).scheme, urlsplit(address).netloc), ("https", "rafs.app"))
        self.assertEqual(urlsplit(page.values("property", "og:image")[0]).scheme, "https")
        self.assertFalse(any(link.get("hreflang") for link in page.links))
        self.assertNotIn("noindex", " ".join(page.values("name", "robots")).lower())

    def test_public_pages_titles_metadata_and_languages(self):
        pages = (
            ("core:home", "core/home.html", {}),
            ("core:about", "core/about_site.html", {}),
            ("core:community_guidelines", "core/community_guidelines.html", {}),
            ("movies:catalog", "movies/catalog.html", {}),
            ("movies:show_reviews", "movies/reviews.html", {}),
            ("movies:detail", "movies/movie_detail.html", {"movie_id": self.movie.pk}),
            ("profile", "accounts/profile.html", {"username": self.author.username}),
        )
        for name, template, kwargs in pages:
            for language in LANGUAGES:
                with self.subTest(page=name, language=language):
                    response, page = self.get_page(name, language, url_kwargs=kwargs)
                    self.assertEqual(page.title.strip(), html.unescape(TITLE_BASELINE[template][language]["with_year"]))
                    self.assertEqual(page.language, language)
                    self.assertNotIn("noindex", response.get("X-Robots-Tag", "").lower())
                    self.assert_public_meta(page)
                    if name != "core:home":
                        self.assertEqual(page.schemas, [])

    def test_home_has_one_website_in_initial_html_and_visible_russian_brand(self):
        description = "RAFS is a site for ratings and reviews of films, series and anime"
        for language in LANGUAGES:
            with self.subTest(language=language):
                response, page = self.get_page("core:home", language)
                self.assertEqual(len(page.schemas), 1)
                schema = json.loads(page.schemas[0])
                self.assertEqual(schema, WEBSITE)
                self.assertEqual(schema["name"], "RAFS")
                self.assertEqual(schema["alternateName"], ["Рафс", "rafs.app"])
                self.assertEqual(schema["url"], "https://rafs.app/")
                self.assertEqual(schema["@id"], "https://rafs.app/#website")
                self.assertNotIn("SearchAction", page.schemas[0])
                with translation.override(language):
                    self.assertEqual(page.home_description.strip(), translation.gettext(description))
                if language != "en":
                    self.assertNotEqual(page.home_description.strip(), description)
                if language == "ru":
                    self.assertIn("RAFS (Рафс) – сайт", page.home_description)

    def test_new_descriptions_are_translated_and_specific_to_each_page(self):
        names = ("core:home", "core:about", "movies:catalog", "movies:show_reviews")
        english = {name: self.get_page(name)[1].values("name", "description")[0] for name in names}
        for language in LANGUAGES:
            descriptions = []
            for name in names:
                _, page = self.get_page(name, language)
                description = page.values("name", "description")[0]
                descriptions.append(description)
                self.assertEqual(page.values("property", "og:description"), [description])
                if language != "en":
                    self.assertNotEqual(description, english[name])
            self.assertEqual(len(set(descriptions)), len(names))

    def test_cookie_language_is_respected_without_fake_language_urls(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ru"
        _, page = self.get_page("core:home", "en")
        self.assertEqual(page.language, "ru")
        self.assertEqual(page.canonical, ["https://rafs.app/"])
        self.assertFalse(any(link.get("hreflang") for link in page.links))

    def test_pagination_is_self_canonical_with_tracking_and_ui_parameters_removed(self):
        for name in ("movies:catalog", "movies:show_reviews"):
            path = reverse(name)
            for requested, resolved in (("2", 2), ("last", 1), ("999", 2), ("invalid", 1), ("1", 1)):
                with self.subTest(page=name, requested=requested):
                    _, page = self.get_page(name, data={"page": requested, "utm_source": "test",
                                                        "email": "private@example.org", "replies": "1"})
                    expected = PUBLIC_ORIGIN + path + ("?page=2" if resolved == 2 else "")
                    self.assertEqual(page.canonical, [expected])
                    self.assertEqual(page.values("property", "og:url"), [expected])
        _, page = self.get_page("movies:catalog", data={"year_from": "2000", "page": "2"})
        self.assertEqual(page.canonical, ["https://rafs.app/movies/?year_from=2000&page=2"])

    def test_sitemap_and_robots_have_public_urls_only_even_on_localhost(self):
        response = self.client.get(reverse("sitemap"), HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 200)
        root = ElementTree.fromstring(response.content)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locations = [node.text for node in root.findall("s:url/s:loc", ns)]
        expected = {PUBLIC_ORIGIN + reverse(name) for name in
                    ("core:home", "core:about", "movies:catalog", "movies:show_reviews", "core:community_guidelines")}
        expected.update(PUBLIC_ORIGIN + reverse("movies:detail", args=[pk]) for pk in Movie.objects.values_list("pk", flat=True))
        self.assertEqual(set(locations), expected)
        self.assertEqual(len(locations), len(expected))
        self.assertFalse(root.findall("s:url/s:lastmod", ns))
        self.assertFalse(root.findall(".//{http://www.w3.org/1999/xhtml}link"))
        robots = self.client.get(reverse("robots"), HTTP_HOST="localhost")
        self.assertEqual(robots.status_code, 200)
        self.assertTrue(robots["Content-Type"].startswith("text/plain"))
        parser = RobotFileParser()
        parser.parse(robots.content.decode().splitlines())
        self.assertEqual(parser.site_maps(), ["https://rafs.app/sitemap.xml"])
        for location in locations:
            self.assertTrue(parser.can_fetch("Googlebot", location))
        self.assertFalse(parser.can_fetch("Googlebot", "https://rafs.app/admin/"))

    def test_movies_have_regular_html_links_without_javascript(self):
        for name in ("core:home", "movies:catalog", "movies:show_reviews"):
            response, page = self.get_page(name)
            if name == "core:home":
                movies = response.context["top_movies"]
            elif name == "movies:catalog":
                movies = response.context["page_obj"].object_list
            else:
                movies = [review.movie for review in response.context["reviews"]]
            self.assertTrue(movies)
            for movie in movies:
                self.assertIn(reverse("movies:detail", args=[movie.pk]), [anchor.get("href") for anchor in page.anchors])

    def test_movie_description_uses_name_year_and_plot_without_html_injection(self):
        self.movie.name = 'SEO "Film" <meta name="description" content="injected">'
        self.movie.description = '<p>A plot "quoted" & distinctive.</p><meta name="robots" content="noindex">'
        self.movie.cover_url = "http://image.tmdb.org/t/p/w500/poster.jpg"
        self.movie.save()
        _, page = self.get_page("movies:detail", url_kwargs={"movie_id": self.movie.pk})
        self.assert_public_meta(page)
        description = page.values("name", "description")[0]
        self.assertIn(self.movie.name, description)
        self.assertIn("(2024)", description)
        self.assertIn('A plot "quoted" & distinctive.', description)
        self.assertEqual(page.values("name", "robots"), [])
        self.assertEqual(page.values("property", "og:image"), ["https://image.tmdb.org/t/p/w500/poster.jpg"])

    def test_missing_movie_description_keeps_localized_fallback_and_optional_year(self):
        self.movie.description = ""
        self.movie.year = None
        self.movie.save()
        response, page = self.get_page("movies:detail", "ru", url_kwargs={"movie_id": self.movie.pk})
        self.assert_public_meta(page)
        self.assertIn(self.movie.name, page.values("name", "description")[0])
        self.assertIn("Оценки и рецензии зрителей", page.values("name", "description")[0])
        self.assertNotIn("None", page.title)
