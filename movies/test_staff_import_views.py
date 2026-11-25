"""Staff page: TMDB search and full import through the views; remote payloads are fixtures."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import ERROR, SUCCESS, get_messages
from django.test import Client
from django.urls import reverse

from movies.management.commands.import_popular_movies import TMDB
from movies.models import Movie
from movies.test_title_import import FixtureWebAPI, FreshCacheTestCase, matrix_api, translated
from movies.services.title_import import POSTER_BASE

SEARCH = reverse("movies:wikidata_search")
TMDB_ADD = reverse("movies:tmdb_import_item")
QID_ADD = reverse("movies:wikidata_add_by_qid")


class SearchFixtureAPI(FixtureWebAPI):
    """Adds the two search endpoints to the import fixtures."""

    results = []
    external = {}

    def get(self, url, params=None):
        if url == f"{TMDB}/search/multi":
            self.calls.append((url, dict(params or {})))
            if not self.has_tmdb:
                return super().get(f"{TMDB}/movie/0")  # raises not_configured like the real client
            return {"page": 1, "results": list(self.results)}
        if url.endswith("/external_ids"):
            self.calls.append((url, {}))
            return self.external.get(url.split("/")[-3] + "/" + url.split("/")[-2], {})
        return super().get(url, params)


def search_api(token="fixture-secret-token"):
    api = SearchFixtureAPI(tmdb=matrix_api().tmdb, documents=matrix_api().documents, token=token)
    api.results = [
        {"media_type": "movie", "id": 603, "title": "Матрица", "original_title": "The Matrix",
         "release_date": "1999-03-31", "poster_path": "/matrix.jpg", "overview": "Хакер узнаёт правду."},
        {"media_type": "tv", "id": 1399, "name": "Игра престолов", "original_name": "Game of Thrones",
         "first_air_date": "2011-04-17", "poster_path": None},
        {"media_type": "person", "id": 6384, "name": "Keanu Reeves"},
    ]
    api.external = {"movie/603": {"wikidata_id": "Q83495", "imdb_id": "tt0133093"},
                    "tv/1399": {"wikidata_id": "Q23572", "imdb_id": "tt0944947"}}
    return api


def use(api):
    return patch("movies.services.title_import.WebAPI.from_settings", return_value=api)


class StaffImportViewTests(FreshCacheTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(username="editor", email="editor@example.com", is_staff=True)

    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)

    def messages(self, response):
        return [(m.level, str(m)) for m in get_messages(response.wsgi_request)]

    def test_tmdb_add_creates_a_complete_title_and_returns_to_the_search(self):
        back = SEARCH + "?query=matrix"
        with use(matrix_api()):
            response = self.client.post(TMDB_ADD, {"media_type": "movie", "tmdb_id": "603", "next": back})
        movie = Movie.objects.get()
        self.assertRedirects(response, back, fetch_redirect_response=False)
        self.assertEqual(self.messages(response), [(SUCCESS, "“The Matrix” was added to the catalogue.")])
        self.assertEqual(movie.cover_url, POSTER_BASE + "/matrix.jpg")
        self.assertEqual(movie.description, "A hacker learns the truth.")
        self.assertEqual(translated(movie, "ru", "wikidata_name"), "Матрица")
        self.assertEqual(translated(movie.actors.get(), "ru", "name"), "Киану Ривз")
        self.assertEqual(translated(movie.genres.get(), "en", "name"), "science fiction film")

    def test_adding_again_does_not_duplicate(self):
        for _ in range(2):
            with use(matrix_api()):
                response = self.client.post(TMDB_ADD, {"media_type": "movie", "tmdb_id": "603"})
        self.assertEqual(Movie.objects.count(), 1)
        # The first redirect is not followed, so both messages are still queued.
        self.assertIn("already in the catalogue", self.messages(response)[-1][1])

    def test_identity_conflict_returns_to_the_search_with_an_explanation(self):
        Movie.objects.create(wikidata_id="Q999", imdb_id="tt0133093", name="Other record")
        back = SEARCH + "?query=matrix&lang=en"
        with use(matrix_api()):
            response = self.client.post(TMDB_ADD, {"media_type": "movie", "tmdb_id": "603", "next": back})
        self.assertRedirects(response, back, fetch_redirect_response=False)
        [(level, text)] = self.messages(response)
        self.assertEqual(level, ERROR)
        self.assertIn("possible duplicate", text)
        self.assertIn("IMDb", text)
        self.assertEqual(Movie.objects.count(), 1)

    def test_invalid_input_is_rejected_before_any_request(self):
        with patch("movies.views.import_tmdb") as run_tmdb, patch("movies.views.import_qid") as run_qid:
            for data in ({"media_type": "person", "tmdb_id": "1"}, {"media_type": "movie", "tmdb_id": "abc"},
                         {"media_type": "tv", "tmdb_id": "0"}, {"media_type": "movie", "tmdb_id": str(2**31)}):
                response = self.client.post(TMDB_ADD, data)
                self.assertRedirects(response, SEARCH, fetch_redirect_response=False)
            for qid in ("P31", "Q0", "Q1; DROP", ""):
                self.client.post(QID_ADD, {"qid": qid})
            self.assertEqual(self.client.post(reverse("movies:wikidata_save_item", args=["X1"])).status_code, 302)
        run_tmdb.assert_not_called()
        run_qid.assert_not_called()

    def test_next_never_leads_off_site(self):
        with patch("movies.views.import_tmdb") as run:
            response = self.client.post(TMDB_ADD, {"media_type": "x", "tmdb_id": "1", "next": "https://evil.example/"})
        self.assertRedirects(response, SEARCH, fetch_redirect_response=False)
        run.assert_not_called()

    def test_add_by_qid_accepts_lowercase_and_takes_the_tmdb_path(self):
        api = matrix_api()
        with use(api):
            response = self.client.post(QID_ADD, {"qid": " q83495 "})
        self.assertTrue(Movie.objects.filter(wikidata_id="Q83495").exists())
        self.assertRedirects(response, SEARCH, fetch_redirect_response=False)
        self.assertIn(f"{TMDB}/movie/603", api.tmdb_requested())

    def test_missing_token_is_explained_without_a_500(self):
        with use(matrix_api(token="")):
            response = self.client.post(TMDB_ADD, {"media_type": "movie", "tmdb_id": "603"})
        [(level, text)] = self.messages(response)
        self.assertEqual(level, ERROR)
        self.assertIn("TMDB_READ_TOKEN", text)
        self.assertFalse(Movie.objects.exists())


class StaffSearchViewTests(FreshCacheTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(username="editor", email="editor@example.com", is_staff=True)

    def setUp(self):
        super().setUp()
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.staff)

    def test_tmdb_results_show_poster_type_year_original_title_and_catalogue_mark(self):
        existing = Movie.objects.create(wikidata_id="Q83495", name="The Matrix")
        api = search_api()
        with use(api):
            response = self.client.get(SEARCH, {"query": "матрица", "lang": "ru"})
        self.assertEqual(response.status_code, 200)
        search_call = api.calls[0][1]
        self.assertEqual((search_call["query"], search_call["language"]), ("матрица", "ru-RU"))
        self.assertContains(response, 'src="https://image.tmdb.org/t/p/w154/matrix.jpg"')
        self.assertContains(response, "The Matrix")
        self.assertContains(response, "1999")
        self.assertContains(response, "Game of Thrones")
        self.assertContains(response, f'href="{reverse("movies:detail", args=[existing.pk])}"', count=1)
        self.assertContains(response, 'name="media_type" value="tv"')
        self.assertContains(response, 'name="tmdb_id" value="1399"')
        self.assertContains(response, f'action="{TMDB_ADD}"', count=2)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertNotContains(response, "Keanu Reeves")  # people are not titles

    def test_missing_token_shows_a_configuration_hint(self):
        with use(search_api(token="")):
            response = self.client.get(SEARCH, {"query": "matrix", "lang": "en"})
        self.assertContains(response, "TMDB_READ_TOKEN")

    def test_wikidata_fallback_marks_titles_already_in_the_catalogue(self):
        existing = Movie.objects.create(wikidata_id="Q123", name="Fixture movie")
        with patch("movies.views.search_wikidata_media", return_value=[
            {"id": "Q123", "title": "Fixture movie", "description": ""},
            {"id": "Q124", "title": "New movie", "description": ""},
        ]):
            response = self.client.get(SEARCH, {"query": "Fixture", "lang": "de", "source": "wikidata"})
        self.assertContains(response, f'href="{reverse("movies:detail", args=[existing.pk])}"', count=1)
        self.assertContains(response, 'action="/movies/wikidata/items/Q124/save/"')
