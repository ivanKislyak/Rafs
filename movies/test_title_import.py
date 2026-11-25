"""Single-title import core: real details/resolve/entities/import_one, remote payloads are fixtures."""

import copy
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from movies.management.commands.import_popular_movies import SPARQL, TMDB, WIKIDATA
from movies.models import Movie
from movies.movie_models import Genre, Person
from movies.services import title_import
from movies.services.title_import import POSTER_BASE, StaffImportError, WebAPI, import_qid, import_tmdb

TOKEN = "fixture-secret-token"


def statement(value):
    return {"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": value}}}


def item_claims(**props):
    claims = {}
    for prop, values in props.items():
        claims[prop] = [statement({"id": v} if isinstance(v, str) and v.startswith("Q") else v) for v in values]
    return claims


def labelled(qid, **labels):
    return {"id": qid, "labels": {lang: {"language": lang, "value": text} for lang, text in labels.items()}}


def matrix_details():
    return {
        "id": 603, "title": "The Matrix", "release_date": "1999-03-31", "overview": "A hacker learns the truth.",
        "poster_path": "/matrix.jpg", "popularity": 88.5, "adult": False, "video": False,
        "external_ids": {"imdb_id": "tt0133093", "wikidata_id": "Q83495"},
        "translations": {"translations": [
            {"iso_639_1": "ru", "iso_3166_1": "RU", "data": {"title": "Матрица", "overview": "Хакер узнаёт правду."}},
            {"iso_639_1": "de", "iso_3166_1": "DE", "data": {"title": "Matrix", "overview": "Ein Hacker erfährt die Wahrheit."}},
        ]},
    }


def matrix_entity():
    entity = labelled("Q83495", en="The Matrix", ru="Матрица")
    entity["descriptions"] = {"en": {"language": "en", "value": "1999 film"}}
    entity["claims"] = item_claims(
        P31=["Q11424"], P136=["Q200"], P495=["Q30"], P272=["Q400"], P161=["Q500"], P57=["Q600"],
        P345=["tt0133093"], P4947=["603"], P577=[{"time": "+1999-03-31T00:00:00Z"}],
    )
    return entity


RELATED = {
    "Q11424": labelled("Q11424", en="film", ru="фильм"),
    "Q5398426": labelled("Q5398426", en="television series", ru="телесериал"),
    "Q200": labelled("Q200", en="science fiction film", ru="научно-фантастический фильм", de="Science-Fiction-Film"),
    "Q30": labelled("Q30", en="United States", ru="США"),
    "Q400": labelled("Q400", en="Warner Bros."),
    "Q500": labelled("Q500", en="Keanu Reeves", ru="Киану Ривз"),
    "Q600": labelled("Q600", en="Lana Wachowski"),
}


class FreshCacheTestCase(TestCase):
    """django-parler keeps translations in the default cache, which outlives the test rollback.

    SQLite reuses primary keys after a rollback, so a later test would read this
    test's cached titles. Clear the cache around every test that writes translations.
    """

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)


class FixtureWebAPI(WebAPI):
    """Only the remote payloads are fixtures; details/resolve/entities run as in production."""

    def __init__(self, tmdb=None, documents=None, bindings=None, token=TOKEN):
        super().__init__(token)
        self.tmdb = tmdb or {}
        self.documents = {**RELATED, **(documents or {})}
        self.bindings = bindings or []
        self.calls = []

    def get(self, url, params=None):
        params = dict(params or {})
        self.calls.append((url, params))
        if url == SPARQL:
            return {"results": {"bindings": copy.deepcopy(self.bindings)}}
        if url == WIKIDATA:
            ids = params["ids"].split("|")
            return {"entities": {qid: copy.deepcopy(self.documents.get(qid, {"id": qid, "missing": ""})) for qid in ids}}
        for media in ("movie", "tv"):
            prefix = f"{TMDB}/{media}/"
            if url.startswith(prefix):
                if not self.has_tmdb:
                    raise StaffImportError("not_configured")
                return copy.deepcopy(self.tmdb.get((media, int(url[len(prefix):]))))
        raise AssertionError(f"Unexpected fixture URL {url}")

    def tmdb_requested(self):
        return [url for url, _ in self.calls if url.startswith(TMDB)]


def matrix_api(documents=None, **changes):
    tmdb = {("movie", 603): matrix_details()}
    return FixtureWebAPI(tmdb=tmdb, documents={"Q83495": matrix_entity(), **(documents or {})}, **changes)


def translated(obj, lang, field):
    row = obj.translations.filter(language_code=lang).first()
    return getattr(row, field, "") if row else ""


class TmdbImportTests(FreshCacheTestCase):
    def test_creates_title_as_complete_as_the_bulk_import(self):
        result = import_tmdb("movie", 603, api=matrix_api())
        movie = Movie.objects.get()
        self.assertTrue(result.created)
        self.assertEqual(result.movie, movie)
        self.assertEqual((movie.wikidata_id, movie.imdb_id, movie.year), ("Q83495", "tt0133093", 1999))
        self.assertEqual(movie.name, "The Matrix")
        self.assertEqual(movie.description, "A hacker learns the truth.")
        self.assertEqual(movie.cover_url, POSTER_BASE + "/matrix.jpg")
        self.assertEqual(movie.tmdb_popularity, 88.5)
        self.assertIsNotNone(movie.last_synced_at)
        self.assertEqual(translated(movie, "ru", "wikidata_name"), "Матрица")
        self.assertEqual(translated(movie, "de", "wikidata_description"), "Ein Hacker erfährt die Wahrheit.")
        self.assertEqual(translated(movie.type_of_work, "ru", "name"), "фильм")
        genre = movie.genres.get()
        self.assertEqual((translated(genre, "en", "name"), translated(genre, "de", "name")),
                         ("science fiction film", "Science-Fiction-Film"))
        actor = movie.actors.get()
        self.assertEqual((translated(actor, "en", "name"), translated(actor, "ru", "name")), ("Keanu Reeves", "Киану Ривз"))
        self.assertEqual(translated(movie.director.get(), "en", "name"), "Lana Wachowski")
        self.assertEqual(translated(movie.studio.get(), "en", "name"), "Warner Bros.")
        self.assertEqual(translated(movie.countries.get(), "ru", "name"), "США")

    def test_repeated_import_finds_the_same_title(self):
        import_tmdb("movie", 603, api=matrix_api())
        result = import_tmdb("movie", 603, api=matrix_api())
        self.assertFalse(result.created)
        self.assertEqual(Movie.objects.count(), 1)
        self.assertEqual(Genre.objects.count(), 1)
        self.assertEqual(result.movie.actors.count(), 1)

    def test_local_cover_is_kept_and_existing_fields_are_not_overwritten(self):
        Movie.objects.create(wikidata_id="Q83495", name="Matrix (local)", cover="movie_covers/local.jpg")
        result = import_tmdb("movie", 603, api=matrix_api())
        movie = Movie.objects.get()
        self.assertFalse(result.created)
        self.assertEqual(movie.name, "Matrix (local)")
        self.assertEqual(movie.cover_url, "")

    def test_imdb_conflict_is_reported_and_nothing_is_created(self):
        Movie.objects.create(wikidata_id="Q999", imdb_id="tt0133093", name="Other record")
        with self.assertRaises(StaffImportError) as raised:
            import_tmdb("movie", 603, api=matrix_api())
        self.assertEqual(raised.exception.code, "rejected")
        self.assertIn("IMDb", raised.exception.detail)
        self.assertEqual(Movie.objects.count(), 1)

    def test_same_title_and_year_without_ids_blocks_a_likely_duplicate(self):
        Movie.objects.create(name="The Matrix", year=1999)
        with self.assertRaises(StaffImportError) as raised:
            import_tmdb("movie", 603, api=matrix_api())
        self.assertEqual(raised.exception.code, "rejected")
        self.assertEqual(Movie.objects.count(), 1)

    def test_no_unique_wikidata_match(self):
        details = matrix_details()
        details["external_ids"] = {"imdb_id": "tt0133093", "wikidata_id": ""}
        api = FixtureWebAPI(tmdb={("movie", 603): details}, bindings=[])
        with self.assertRaises(StaffImportError) as raised:
            import_tmdb("movie", 603, api=api)
        self.assertEqual(raised.exception.code, "no_wikidata")
        self.assertFalse(Movie.objects.exists())

    def test_adult_title_is_refused(self):
        details = matrix_details()
        details["adult"] = True
        with self.assertRaises(StaffImportError) as raised:
            import_tmdb("movie", 603, api=FixtureWebAPI(tmdb={("movie", 603): details}))
        self.assertEqual(raised.exception.code, "adult")

    def test_invalid_input_and_missing_token(self):
        for media_type, tmdb_id in (("person", 1), ("movie", 0), ("movie", True), ("tv", 2**31)):
            with self.assertRaises(StaffImportError) as raised:
                import_tmdb(media_type, tmdb_id, api=matrix_api())
            self.assertEqual(raised.exception.code, "invalid")
        with self.assertRaises(StaffImportError) as raised:
            import_tmdb("movie", 603, api=matrix_api(token=""))
        self.assertEqual(raised.exception.code, "not_configured")


class TvImportTests(FreshCacheTestCase):
    def tv(self, p31):
        details = {
            "id": 1399, "name": "Game of Thrones", "first_air_date": "2011-04-17", "overview": "Noble families.",
            "poster_path": "/got.jpg", "popularity": 12.0,
            "external_ids": {"imdb_id": "tt0944947", "wikidata_id": "Q23572"}, "translations": {"translations": []},
        }
        entity = labelled("Q23572", en="Game of Thrones")
        entity["claims"] = item_claims(P31=[p31], P345=["tt0944947"], P4983=["1399"])
        return FixtureWebAPI(tmdb={("tv", 1399): details}, documents={"Q23572": entity})

    def test_whole_series_with_confirmed_type_is_imported(self):
        result = import_tmdb("tv", 1399, api=self.tv("Q5398426"))
        self.assertEqual(result.movie.type_of_work.wikidata_id, "Q5398426")
        self.assertEqual(result.movie.year, 2011)

    def test_tv_without_confirmed_series_type_is_not_imported(self):
        with self.assertRaises(StaffImportError) as raised:
            import_tmdb("tv", 1399, api=self.tv("Q11424"))
        self.assertEqual(raised.exception.code, "rejected")
        self.assertFalse(Movie.objects.exists())


class QidImportTests(FreshCacheTestCase):
    def test_qid_with_tmdb_id_takes_the_full_tmdb_path(self):
        api = matrix_api()
        result = import_qid("Q83495", api=api)
        self.assertTrue(result.created)
        self.assertIn(f"{TMDB}/movie/603", api.tmdb_requested())
        self.assertEqual(result.movie.cover_url, POSTER_BASE + "/matrix.jpg")

    def test_qid_whose_tmdb_record_points_elsewhere_is_a_conflict(self):
        other = labelled("Q1000", en="Not the Matrix")
        other["claims"] = item_claims(P31=["Q11424"], P4947=["603"])
        api = matrix_api(documents={"Q1000": other, "Q83495": matrix_entity()})
        with self.assertRaises(StaffImportError) as raised:
            import_qid("Q1000", api=api)
        self.assertEqual(raised.exception.code, "identity_conflict")
        self.assertFalse(Movie.objects.exists())

    def test_qid_with_two_tmdb_ids_is_ambiguous(self):
        entity = labelled("Q1001", en="Twice")
        entity["claims"] = item_claims(P31=["Q11424"], P4947=["1", "2"])
        with self.assertRaises(StaffImportError) as raised:
            import_qid("Q1001", api=FixtureWebAPI(documents={"Q1001": entity}))
        self.assertEqual(raised.exception.code, "ambiguous")

    def test_wikidata_only_title_gets_named_relations_without_tmdb(self):
        entity = labelled("Q1002", en="Obscure Short Film", ru="Малоизвестный фильм")
        entity["descriptions"] = {"en": {"language": "en", "value": "2004 film"}}
        entity["claims"] = item_claims(P31=["Q11424"], P136=["Q200"], P161=["Q500"],
                                       P577=[{"time": "+2004-00-00T00:00:00Z"}])
        api = FixtureWebAPI(documents={"Q1002": entity}, token="")
        result = import_qid("Q1002", api=api)
        movie = result.movie
        self.assertEqual(api.tmdb_requested(), [])
        self.assertEqual((movie.name, movie.year, movie.description), ("Obscure Short Film", 2004, "2004 film"))
        self.assertEqual(translated(movie, "ru", "wikidata_name"), "Малоизвестный фильм")
        self.assertEqual(translated(movie.actors.get(), "ru", "name"), "Киану Ривз")
        self.assertEqual(translated(movie.type_of_work, "en", "name"), "film")
        self.assertEqual(movie.cover_url, "")

    def test_item_that_is_not_a_work_is_refused(self):
        entity = labelled("Q1003", en="A person")
        entity["claims"] = item_claims(P31=["Q5"])
        documents = {"Q1003": entity, "Q5": {"id": "Q5", "claims": {}}}
        with self.assertRaises(StaffImportError) as raised:
            import_qid("Q1003", api=FixtureWebAPI(documents=documents))
        self.assertEqual(raised.exception.code, "not_a_work")

    def test_invalid_qid(self):
        for value in ("", "Q0", "P31", "Q12; DROP"):
            with self.assertRaises(StaffImportError) as raised:
                import_qid(value, api=FixtureWebAPI())
            self.assertEqual(raised.exception.code, "invalid")


def response(status, payload=None, headers=None):
    mock = MagicMock(status_code=status, headers=headers or {})
    mock.json.return_value = payload if payload is not None else {}
    return mock


@patch.object(title_import.time, "sleep")
@patch.object(title_import.random, "uniform", return_value=0)
class WebApiHttpTests(SimpleTestCase):
    def api(self, *responses):
        api = WebAPI(TOKEN)
        api.session.get = MagicMock(side_effect=list(responses))
        return api

    def test_retries_429_and_5xx_then_returns_the_payload(self, uniform, sleep):
        api = self.api(response(429, headers={"Retry-After": "1"}), response(503), response(200, {"id": 1}))
        self.assertEqual(api.get(f"{TMDB}/movie/1"), {"id": 1})
        self.assertEqual(api.session.get.call_count, 3)
        headers = api.session.get.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer " + TOKEN)
        self.assertEqual(api.session.get.call_args.kwargs["timeout"], WebAPI.TIMEOUT)
        self.assertIn("RafsCatalogImporter", api.session.headers["User-Agent"])

    def test_gives_up_without_hanging_and_never_logs_the_token(self, uniform, sleep):
        api = self.api(response(500), response(502), response(504))
        with self.assertLogs("movies.services.title_import", "WARNING") as logs, \
                self.assertRaises(StaffImportError) as raised:
            api.get(f"{TMDB}/movie/1")
        self.assertEqual(raised.exception.code, "source_unavailable")
        self.assertNotIn(TOKEN, "\n".join(logs.output))
        self.assertNotIn(TOKEN, str(raised.exception) + raised.exception.detail)

    def test_long_retry_after_stops_at_once(self, uniform, sleep):
        api = self.api(response(429, headers={"Retry-After": "120"}))
        with self.assertLogs("movies.services.title_import", "WARNING"), self.assertRaises(StaffImportError):
            api.get(f"{TMDB}/movie/1")
        self.assertEqual(api.session.get.call_count, 1)
        sleep.assert_not_called()

    def test_access_errors_and_timeouts(self, uniform, sleep):
        with self.assertLogs("movies.services.title_import", "WARNING"), self.assertRaises(StaffImportError) as raised:
            self.api(response(401)).get(f"{TMDB}/movie/1")
        self.assertEqual(raised.exception.code, "source_access")
        api = self.api(*[requests.Timeout(f"https://api.themoviedb.org/3/movie/1?api_key={TOKEN}")] * 3)
        with self.assertLogs("movies.services.title_import", "WARNING") as logs, self.assertRaises(StaffImportError):
            api.get(f"{TMDB}/movie/1")
        self.assertNotIn(TOKEN, "\n".join(logs.output))

    def test_missing_credentials_never_reach_tmdb(self, uniform, sleep):
        api = WebAPI("", "")
        api.session.get = MagicMock()
        with self.assertRaises(StaffImportError) as raised:
            api.get(f"{TMDB}/movie/1")
        self.assertEqual(raised.exception.code, "not_configured")
        api.session.get.assert_not_called()

    def test_wikidata_maxlag_body_is_retried(self, uniform, sleep):
        api = self.api(response(200, {"error": {"code": "maxlag"}}), response(200, {"entities": {}}))
        self.assertEqual(api.get(WIKIDATA, {"ids": "Q1"}), {"entities": {}})

    def test_not_found_is_none_and_cached(self, uniform, sleep):
        api = self.api(response(404))
        self.assertIsNone(api.get(f"{TMDB}/movie/1"))
        self.assertIsNone(api.get(f"{TMDB}/movie/1"))
        self.assertEqual(api.session.get.call_count, 1)
