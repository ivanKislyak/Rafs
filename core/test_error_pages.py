from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import translation
from django.views.defaults import server_error


class NotFoundPageTests(TestCase):
    """404 keeps the full site layout: header, footer and the signed-in account menu."""

    def test_unknown_url_renders_the_site_layout(self):
        response = self.client.get("/no-such-page/", HTTP_ACCEPT_LANGUAGE="en")
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "404.html")
        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, "<title>Page not found · RAFS</title>", html=True, status_code=404)
        self.assertContains(response, '<meta name="robots" content="noindex">', html=True, status_code=404)
        self.assertContains(response, "main-header", status_code=404)
        self.assertContains(response, "main-footer", status_code=404)
        self.assertContains(response, "css/error-page.css", status_code=404)

    def test_signed_in_user_keeps_the_account_menu(self):
        user = get_user_model().objects.create_user(username="lost-visitor", email="lost@example.com")
        self.client.force_login(user)
        response = self.client.get("/no-such-page/")
        self.assertContains(response, "lost-visitor", status_code=404)

    def test_missing_playlist_uses_the_same_page(self):
        response = self.client.get("/movies/playlist/missing/")
        self.assertTemplateUsed(response, "404.html")

    def test_page_is_translated(self):
        for language, heading in [("ru", "Страница не найдена"), ("de", "Seite nicht gefunden")]:
            with self.subTest(language=language):
                response = self.client.get("/no-such-page/", HTTP_ACCEPT_LANGUAGE=language)
                self.assertContains(response, f"<h1>{heading}</h1>", html=True, status_code=404)


class ServerErrorPageTests(TestCase):
    """500 is rendered with an empty context, so it must not depend on the request or the database."""

    def render(self, language="en"):
        with translation.override(language):
            return server_error(RequestFactory().get("/"))

    def test_renders_standalone_without_queries(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.render()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(queries), 0)
        html = response.content.decode()
        self.assertIn("<title>Something went wrong · RAFS</title>", html)
        self.assertIn("main-header", html)
        self.assertIn("css/error-page.css", html)
        self.assertIn('href="/"', html)

    def test_page_is_translated(self):
        for language, heading in [("ru", "Что-то пошло не так"), ("uk", "Щось пішло не так")]:
            with self.subTest(language=language):
                self.assertIn(f"<h1>{heading}</h1>", self.render(language).content.decode())

    def test_unhandled_exception_shows_the_page(self):
        self.client.raise_request_exception = False
        with patch("core.views.HomePageView.get_context_data", side_effect=RuntimeError("boom")):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Something went wrong", response.content.decode())
