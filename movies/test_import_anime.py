"""Importer checks use fixtures and an isolated Django test database, never TMDB."""

import copy
import io
import sqlite3
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from movies.management.commands import import_anime as anime
from movies.management.commands import import_popular_movies as popular
from movies.models import Movie, Review
from movies.movie_models import Genre, TypeOfWork

LANGUAGES = ["en", "ru", "uk", "kk", "es", "de"]


def statement(value):
    return {"mainsnak": {"snaktype": "value", "datavalue": {"value": value}}}


def entity(qid, **claims):
    return {
        "id": qid,
        "labels": {lang: {"value": f"{lang} {qid}"} for lang in LANGUAGES},
        "claims": {prop: [statement({"id": value} if value.startswith("Q") else value)
                          for value in values] for prop, values in claims.items()},
    }


def detail(media_type, tmdb_id=42):
    title, date, _ = popular.MEDIA_FIELDS[media_type]
    return {
        "id": tmdb_id, title: f"Anime {media_type}", date: "2001-07-20",
        "genres": [{"id": 16}], "vote_count": 0,
        "overview": "English synopsis", "poster_path": "/poster.jpg",
        "external_ids": {"wikidata_id": "Q101" if media_type == "movie" else "Q102",
                         "imdb_id": "tt101" if media_type == "movie" else "tt102"},
        "keywords": {"keywords" if media_type == "movie" else "results": [{"id": 210024}]},
        "translations": {"translations": [
            {"iso_639_1": lang, "iso_3166_1": popular.REGIONS[lang],
             "data": {title: f"{lang} {media_type}", "overview": f"{lang} synopsis"}}
            for lang in LANGUAGES
        ]},
    }


class FixtureAPI(anime.AnimeAPI):
    """Exercise the real endpoint selection, resolver and cache-free entities."""

    documents = {
        "Q101": entity("Q101", P31=["Q20650540"], P4947=["42"], P345=["tt101"], P136=["Q900"]),
        "Q102": entity("Q102", P31=["Q63952888"], P4983=["42"], P345=["tt102"], P136=["Q900"]),
        "Q20650540": entity("Q20650540", P279=["Q11424"]),
        "Q63952888": entity("Q63952888", P279=["Q5398426"]),
        "Q900": entity("Q900"),
    }

    def get(self, url, params=None):
        if url.endswith("/keyword/210024"):
            return {"id": 210024, "name": "anime"}
        if url.endswith("/configuration"):
            return {"images": {"secure_base_url": "https://image.tmdb.org/t/p/", "poster_sizes": ["w500"]}}
        if "/discover/" in url:
            return {"results": [{"id": 42}], "total_pages": 1}
        for media_type in ("movie", "tv"):
            if url.endswith(f"/{media_type}/42"):
                return detail(media_type)
        raise AssertionError(f"Unexpected fixture endpoint: {url}")

    def entities(self, qids, claims=False):
        return {qid: copy.deepcopy(self.documents.get(qid, {})) for qid in qids}


class StateAndFormatTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = anime.AnimeState(self.temp.name)
        self.addCleanup(self.state.db.close)

    def test_movie_and_tv_same_number_have_independent_state_and_dry_run(self):
        with self.state.db:
            self.state.db.executemany("INSERT INTO manifest(media_type,tmdb_id) VALUES (?,42)", [("movie",), ("tv",)])
        self.state.mark("movie", 42, "created", 10)
        self.state.mark("tv", 42, "skipped", reason="fixture", dry_run=True)
        rows = self.state.db.execute("SELECT * FROM manifest ORDER BY position").fetchall()
        self.assertEqual((rows[0]["status"], rows[1]["status"]), ("created", "pending"))
        self.assertEqual(rows[1]["dry_status"], "skipped")
        self.state.report()
        self.assertIn("media_type", (Path(self.temp.name) / "import_report.csv").read_text(encoding="utf-8-sig"))

    def test_old_state_rejected_without_changes(self):
        with tempfile.TemporaryDirectory() as old_directory:
            old = popular.State(old_directory)
            old.set_meta("fixture", {"important": True})
            old.db.close()
            path = Path(old_directory) / "state.sqlite3"
            before = path.read_bytes()
            with self.assertRaisesMessage(CommandError, "import_popular_movies"):
                anime.AnimeState(old_directory)
            self.assertEqual(path.read_bytes(), before)

    def test_same_state_cannot_run_twice(self):
        with popular.run_lock(self.temp.name):
            with self.assertRaises(CommandError):
                with popular.run_lock(self.temp.name):
                    self.fail("Second process lock acquired")

    def test_anime_requires_exact_keyword_and_animation_not_language(self):
        for media_type in ("movie", "tv"):
            item = detail(media_type)
            item["original_language"] = "en"
            anime.validate_candidate(item, media_type, 42, 0)
            with self.assertRaises(anime.ImportIssue):
                anime.validate_candidate(item, media_type, 42, 50)
            item["original_language"] = "ja"
            item["keywords"] = {"keywords": [{"id": 222243}], "results": [{"id": 222243}]}
            with self.assertRaisesMessage(anime.ImportIssue, "точной метки"):
                anime.validate_candidate(item, media_type, 42, 0)
            item = detail(media_type)
            item["genres"] = [{"id": 18}]
            with self.assertRaises(anime.ImportIssue):
                anime.validate_candidate(item, media_type, 42, 0)

    def test_format_subclasses_and_ambiguous_or_partial_works(self):
        api = Mock()
        graph = {
            "Q200": entity("Q200", P279=["Q11424"]),
            "Q201": entity("Q201", P279=["Q5398426"]),
            "Q202": entity("Q202", P279=["Q526877"]),
            "Q203": entity("Q203", P279=["Q3464665"]),
            "Q204": entity("Q204", P279=["Q21191270"]),
            "Q205": entity("Q205", P279=["Q5398426"]),
        }
        api.entities.side_effect = lambda qids, **kwargs: {qid: graph.get(qid, {}) for qid in qids}
        for qid, media_type in (("Q200", "movie"), ("Q201", "tv"), ("Q202", "tv")):
            self.assertEqual(anime.confirmed_format(entity("Q1", P31=[qid]), media_type, api), qid)
        self.assertEqual(anime.confirmed_format(entity("Q1", P31=["Q201", "Q5398426"]), "tv", api), "Q201")
        for types, media_type in ((["Q200"], "tv"), (["Q201"], "movie"), (["Q203"], "tv"),
                                  (["Q204"], "tv"), (["Q201", "Q205"], "tv"), ([], "tv"), (["Q999"], "tv")):
            with self.subTest(types=types), self.assertRaises(anime.ImportIssue):
                anime.confirmed_format(entity("Q1", P31=types), media_type, api)

    def test_discovery_filters_interleaves_and_resumes_without_extra_pages(self):
        api = Mock()
        api.get.return_value = {"results": [{"id": 42}, {"id": 43}], "total_pages": 1}
        options = {"media_type": "both", "limit": 3, "sort": "popularity.desc", "min_votes": 0}
        command = anime.Command(stdout=io.StringIO())
        command.discover(api, self.state, options)
        pairs = list(self.state.db.execute("SELECT media_type,tmdb_id FROM manifest ORDER BY position"))
        self.assertEqual([tuple(row) for row in pairs], [("movie", 42), ("tv", 42), ("movie", 43), ("tv", 43)])
        options["limit"] = 20
        command.discover(api, self.state, options)
        self.assertEqual(api.get.call_count, 2)
        for call in api.get.call_args_list:
            self.assertEqual(call.args[1]["with_keywords"], "210024")
            self.assertEqual(call.args[1]["with_genres"], "16")
            self.assertEqual(call.args[1]["vote_count.gte"], 0)
            self.assertNotIn("with_original_language", call.args[1])

    def test_api_tv_endpoints_and_movie_command_default_are_preserved(self):
        api = anime.AnimeAPI(self.state, "fake-token", "", LANGUAGES, lambda _: None, {})
        self.addCleanup(api.session.close)
        with patch.object(api, "get", return_value={}) as get:
            api.details("tv", 42)
            self.assertEqual(get.call_args.args[0], popular.TMDB + "/tv/42")
            self.assertIn("external_ids,translations,keywords", get.call_args.args[1]["append_to_response"])
        old = popular.API(self.state, "fake-token", "", LANGUAGES, lambda _: None, {})
        self.addCleanup(old.session.close)
        with patch.object(old, "get", return_value={}) as get:
            old.details(42)
            self.assertEqual(get.call_args.args[0], popular.TMDB + "/movie/42")

    def test_retry_after_cache_and_credentials_are_shared_and_not_persisted(self):
        api = anime.AnimeAPI(self.state, "", "private-fixture-key", LANGUAGES, lambda _: None,
                             {"tmdb": 0.6, "wikidata": 1, "sparql": 5})
        self.addCleanup(api.session.close)
        rate_limited = Mock(status_code=429, headers={"Retry-After": "37"})
        success = Mock(status_code=200, headers={})
        success.json.return_value = {"id": 42}
        with patch.object(api.session, "get", side_effect=[rate_limited, success]) as get, \
                patch.object(popular.time, "sleep") as sleep, \
                patch.object(popular.random, "uniform", return_value=0):
            self.assertEqual(api.get(popular.TMDB + "/movie/42"), {"id": 42})
            self.assertTrue(any(call.args[0] > 36 for call in sleep.call_args_list))
            api.get(popular.TMDB + "/movie/42")
            self.assertEqual(get.call_count, 2)
        dump = " ".join(self.state.db.iterdump())
        self.assertNotIn("private-fixture-key", dump)

    def test_maxlag_stops_without_dropping_parameter_or_retrying_unboundedly(self):
        api = anime.AnimeAPI(self.state, "fixture", "", LANGUAGES, lambda _: None,
                             {"tmdb": 0.6, "wikidata": 1, "sparql": 5}, maxlag_wait=0)
        self.addCleanup(api.session.close)
        response = Mock(status_code=200, headers={})
        response.json.return_value = {"error": {"code": "maxlag", "lag": 8}}
        with patch.object(api.session, "get", return_value=response) as get:
            with self.assertRaisesMessage(CommandError, "maxlag"):
                api.entities(["Q101"], claims=True)
            self.assertEqual(get.call_count, 1)
            self.assertEqual(get.call_args.kwargs["params"]["maxlag"], 5)
        self.assertFalse(self.state.db.execute("SELECT * FROM cache").fetchall())


class ImportAnimeTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "anime"
        self.output = io.StringIO()

    def run_command(self, **options):
        with patch.object(anime, "AnimeAPI", FixtureAPI), \
                patch.dict("os.environ", {"TMDB_READ_TOKEN": "fixture-token"}), \
                patch.object(anime.settings, "BASE_DIR", Path(self.temp.name)):
            call_command("import_anime", state_dir=str(self.directory), stdout=self.output,
                         limit=options.pop("limit", 20), **options)

    def state_rows(self):
        with sqlite3.connect(self.directory / "state.sqlite3") as db:
            db.row_factory = sqlite3.Row
            return db.execute("SELECT * FROM manifest ORDER BY position").fetchall()

    def test_dry_run_then_real_then_resume_movie_tv_same_id_and_six_languages(self):
        self.run_command(dry_run=True)
        self.assertEqual(Movie.objects.count(), 0)
        self.assertEqual(TypeOfWork.objects.count(), 0)
        self.assertEqual(Genre.objects.count(), 0)
        self.assertEqual([row["status"] for row in self.state_rows()], ["pending", "pending"])
        self.run_command()
        self.assertEqual(Movie.objects.count(), 2)
        movie = Movie.objects.get(wikidata_id="Q101")
        tv = Movie.objects.get(wikidata_id="Q102")
        self.assertEqual(movie.type_of_work.wikidata_id, "Q20650540")
        self.assertEqual(tv.type_of_work.wikidata_id, "Q63952888")
        self.assertEqual(tv.year, 2001)
        self.assertEqual(tv.cover_url, "https://image.tmdb.org/t/p/w500/poster.jpg")
        self.assertEqual(tv.genres.get().wikidata_id, "Q900")
        for language in LANGUAGES:
            row = tv.translations.get(language_code=language)
            self.assertEqual(row.wikidata_name, f"{language} tv")
            self.assertEqual(row.wikidata_description, f"{language} synopsis")
        before = tv.last_synced_at
        self.run_command()
        tv.refresh_from_db()
        self.assertEqual(tv.last_synced_at, before)
        self.assertEqual(Movie.objects.count(), 2)

    def test_manual_data_reviews_and_existing_relations_preserved(self):
        work_type = TypeOfWork.objects.create(wikidata_id="Q777")
        genre = Genre.objects.create(wikidata_id="Q778")
        movie = Movie.objects.create(wikidata_id="Q102", imdb_id="tt102", name="Manual title",
                                     year=1999, description="Manual synopsis", rate=Decimal("9.2"),
                                     cover="movie_covers/manual.jpg", cover_url="https://example.org/manual.jpg",
                                     type_of_work=work_type)
        popular.fill_translations(movie, {"ru": {"wikidata_name": "Ручное название", "wikidata_description": ""}})
        movie.genres.add(genre)
        author = get_user_model().objects.create_user(username="import-reviewer")
        review = Review.objects.create(movie=movie, user=author, rating=Decimal("8.0"), text="Manual review")
        self.run_command()
        movie.refresh_from_db()
        review.refresh_from_db()
        self.assertEqual((movie.name, movie.year, movie.description, movie.rate),
                         ("Manual title", 1999, "Manual synopsis", Decimal("9.2")))
        self.assertEqual(movie.type_of_work_id, work_type.pk)
        self.assertEqual(movie.cover.name, "movie_covers/manual.jpg")
        self.assertEqual(movie.cover_url, "https://example.org/manual.jpg")
        self.assertEqual(movie.translations.get(language_code="ru").wikidata_name, "Ручное название")
        self.assertEqual(movie.translations.get(language_code="ru").wikidata_description, "ru synopsis")
        self.assertEqual(set(movie.genres.values_list("wikidata_id", flat=True)), {"Q778", "Q900"})
        self.assertEqual((review.text, review.rating), ("Manual review", Decimal("8.0")))

    def test_identity_conflict_and_same_title_never_merge(self):
        Movie.objects.create(name="Anime movie", year=2001)
        Movie.objects.create(wikidata_id="Q103", imdb_id="tt102", name="Different work")
        self.run_command()
        self.assertEqual(Movie.objects.count(), 2)
        self.assertEqual([row["status"] for row in self.state_rows()], ["skipped", "skipped"])
        self.assertIn("названием", self.state_rows()[0]["reason"])
        self.assertIn("Wikidata ID отличается", self.state_rows()[1]["reason"])

    def test_ambiguous_external_identifiers_skip(self):
        document = copy.deepcopy(FixtureAPI.documents["Q102"])
        document["claims"]["P4983"].append(statement("43"))
        with patch.dict(FixtureAPI.documents, {"Q102": document}):
            self.run_command()
        self.assertFalse(Movie.objects.filter(wikidata_id="Q102").exists())
        self.assertIn("Неоднозначная идентичность", self.state_rows()[1]["reason"])

    def test_transaction_rollback_and_resume_after_database_failure(self):
        with patch.object(popular, "relation_data", side_effect=RuntimeError("fixture")):
            with self.assertRaisesMessage(CommandError, "RuntimeError"):
                self.run_command()
        self.assertEqual(Movie.objects.count(), 0)
        self.assertEqual(TypeOfWork.objects.count(), 0)
        self.assertEqual(self.state_rows()[0]["status"], "error")
        self.run_command()
        self.assertEqual(Movie.objects.count(), 2)

    def test_interrupt_rolls_back_current_work_and_continues_next_run(self):
        original = popular.relation_data
        calls = 0

        def interrupt_second(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise KeyboardInterrupt
            return original(*args)

        with patch.object(popular, "relation_data", side_effect=interrupt_second):
            self.run_command()
        self.assertEqual(Movie.objects.count(), 1)
        self.assertEqual([row["status"] for row in self.state_rows()], ["created", "pending"])
        self.run_command()
        self.assertEqual(Movie.objects.count(), 2)

    def test_state_configuration_cannot_be_repurposed(self):
        self.run_command(dry_run=True)
        with self.assertRaisesMessage(CommandError, "другой БД/выборке/языкам"):
            self.run_command(min_votes=50)

    def test_limit_can_increase_without_consuming_remaining_candidates(self):
        self.run_command(limit=1)
        self.assertEqual(Movie.objects.count(), 1)
        self.assertEqual([row["status"] for row in self.state_rows()], ["created", "pending"])
        self.run_command(limit=20)
        self.assertEqual(Movie.objects.count(), 2)

    def test_tv_missing_air_date_uses_wikidata_and_missing_languages_stay_missing(self):
        item = detail("tv")
        item["first_air_date"] = ""
        item["translations"]["translations"] = item["translations"]["translations"][:1]
        data = entity("Q102", P31=["Q5398426"], P4983=["42"], P345=["tt102"])
        data["labels"] = {"en": {"value": "English title"}}
        data["claims"]["P580"] = [statement({"time": "+2001-04-01T00:00:00Z"})]
        data["claims"]["P577"] = [statement({"time": "+2002-01-01T00:00:00Z"})]
        obj, _ = popular.import_one(item, "Q102", data, {}, LANGUAGES, "",
                                     media_type="tv", confirmed_type="Q5398426")
        self.assertEqual(obj.year, 2001)
        self.assertEqual(set(obj.translations.values_list("language_code", flat=True)), {"en"})

    def test_tv_sparql_uses_tv_property_and_rejects_conflicting_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            state = anime.AnimeState(directory)
            self.addCleanup(state.db.close)
            api = anime.AnimeAPI(state, "fixture", "", LANGUAGES, lambda _: None, {})
            self.addCleanup(api.session.close)
            item = detail("tv")
            item["external_ids"].pop("wikidata_id")
            bindings = [
                {"item": {"value": "http://www.wikidata.org/entity/Q102"},
                 "identifier": {"value": "42"}, "source": {"value": "tmdb"}},
                {"item": {"value": "http://www.wikidata.org/entity/Q103"},
                 "identifier": {"value": "tt102"}, "source": {"value": "imdb"}},
            ]
            with patch.object(api, "get", return_value={"results": {"bindings": bindings}}) as get:
                self.assertEqual(api.resolve([item], media_type="tv"), {})
                query = get.call_args.args[1]["query"]
                self.assertIn("wdt:P4983", query)
                self.assertNotIn("wdt:P4947", query)
                self.assertIn("wdt:P345", query)

    def test_shared_movie_import_default_still_handles_missing_type(self):
        item = detail("movie")
        data = entity("Q101", P4947=["42"], P345=["tt101"])
        obj, created = popular.import_one(item, "Q101", data, {}, LANGUAGES, "")
        self.assertTrue(created)
        self.assertEqual(obj.type_of_work.wikidata_id, "Q11424")
        with self.assertRaises(anime.ImportIssue):
            popular.import_one(detail("tv"), "Q102", {}, {}, LANGUAGES, "", media_type="tv")
