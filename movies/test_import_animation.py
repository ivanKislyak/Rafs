"""Mocked HTTP and isolated PostgreSQL checks; never import production data."""

import copy
import io
import json
import signal
import sqlite3
import tempfile
import psycopg
from pathlib import Path
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.search import SearchQuery
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import reverse

from movies.management.commands import import_animation as animation
from movies.management.commands import import_anime as anime
from movies.management.commands import import_popular_movies as popular
from movies.models import AnimationImportReceipt, GlobalSearchIndex, Movie, Review, ReviewVote
from movies.movie_models import Genre, Person, TypeOfWork
from movies.services.animation_state import AnimationState, saved_config
from movies.services.search_index import refresh_movie_documents
from movies.test_import_anime import LANGUAGES, entity, statement


def config(**changes):
    return {
        "importer": "animation-v1", "schema_version": 1, "sources": ["movie", "tv"],
        "date_from": "2020-02-28", "date_to": "2020-03-01", **changes,
    }


def detail(media, number):
    title, released, _ = popular.MEDIA_FIELDS[media]
    code = 1000 + number if media == "movie" else 2000 + number
    return {
        "id": number, title: f"Animated {media} {number}", released: "2001-07-20",
        "genres": [{"id": 16}], "vote_count": 0, "overview": "English synopsis",
        "poster_path": "/poster.jpg", "keywords": {"keywords" if media == "movie" else "results": []},
        "external_ids": {"wikidata_id": f"Q{code}", "imdb_id": f"tt{code}"},
        "translations": {"translations": [
            {"iso_639_1": language, "iso_3166_1": popular.REGIONS[language],
             "data": {title: f"{language} {media} {number}", "overview": f"{language} synopsis"}}
            for language in LANGUAGES
        ]},
    }


class FixtureAPI(anime.AnimeAPI):
    """Exercise real details/resolve/import paths; only remote payloads are fixtures."""

    items = {}
    documents = {}
    bindings = []
    requests = []
    require_outside_atomic = False

    def get(self, url, params=None):
        if self.require_outside_atomic:
            assert not connection.in_atomic_block, "Network request inside Django atomic block"
        params = params or {}
        type(self).requests.append((url, params))
        if url.endswith("/configuration"):
            return {"images": {"secure_base_url": "https://image.tmdb.org/t/p/", "poster_sizes": ["w500"]}}
        if url.endswith("/keyword/210024"):
            return {"id": 210024, "name": "anime"}
        if url == popular.SPARQL:
            return {"results": {"bindings": copy.deepcopy(self.bindings)}}
        for media in ("movie", "tv"):
            if url.endswith("/discover/" + media):
                assert params["page"] <= 500
                assert params["with_genres"] == "16"
                assert "with_original_language" not in params and "with_origin_country" not in params
                assert "with_keywords" not in params
                if "without_keywords" in params:
                    assert params["without_keywords"] == "210024"
                if any(key.endswith(".gte") and "date" in key for key in params):
                    return {"results": [], "total_pages": 0, "total_results": 0}
                ids = sorted(number for kind, number in self.items if kind == media)
                offset = (params["page"] - 1) * 20
                return {"results": [{"id": number} for number in ids[offset:offset + 20]],
                        "total_pages": (len(ids) + 19) // 20, "total_results": len(ids)}
            prefix = f"{popular.TMDB}/{media}/"
            if url.startswith(prefix):
                return copy.deepcopy(self.items.get((media, int(url[len(prefix):]))))
        raise AssertionError("Unexpected fixture URL")

    def entities(self, qids, claims=False):
        if self.require_outside_atomic:
            assert not connection.in_atomic_block
        return {qid: copy.deepcopy(self.documents.get(qid, {})) for qid in qids}


class AnimationStateTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = AnimationState(self.temp.name, config())
        self.addCleanup(self.state.db.close)

    def test_same_number_interleaves_sources_and_page_commit_is_atomic(self):
        pages = [(self.state.next_partition(media), {"results": [{"id": 42}, {"id": 43}], "total_pages": 1})
                 for media in ("movie", "tv")]
        self.state.db.execute("CREATE TRIGGER fixture_failure BEFORE UPDATE ON partitions BEGIN SELECT RAISE(ABORT,'fixture'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.state.save_pages(pages)
        self.assertEqual(self.state.db.execute("SELECT COUNT(*) FROM manifest").fetchone()[0], 0)
        self.assertEqual(self.state.next_partition("movie")["page"], 0)
        self.state.db.execute("DROP TRIGGER fixture_failure")
        self.state.save_pages(pages)
        self.assertEqual([tuple(row) for row in self.state.db.execute("SELECT media_type,tmdb_id FROM manifest ORDER BY position")],
                         [("movie", 42), ("tv", 42), ("movie", 43), ("tv", 43)])
        self.assertEqual(self.state.next_partition("movie")["mode"], "dated")

    def test_overflow_splits_inclusive_dates_across_leap_day(self):
        self.state.db.execute("UPDATE partitions SET status='done' WHERE mode='unfiltered'")
        self.state.db.commit()
        part = self.state.next_partition("movie")
        self.state.save_pages([(part, {"results": [{"id": 1}], "total_pages": 501, "total_results": 10001})])
        children = self.state.db.execute("SELECT lower_date,upper_date FROM partitions WHERE media_type='movie' AND status='pending' ORDER BY id").fetchall()
        self.assertEqual([tuple(row) for row in children], [("2020-02-28", "2020-02-29"), ("2020-03-01", "2020-03-01")])
        self.assertEqual(self.state.candidates(10)[0]["tmdb_id"], 1)

    def test_indivisible_overflow_downloads_at_most_500_pages_and_reports_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            state = AnimationState(directory, config(sources=["tv"], date_from="2020-02-29", date_to="2020-02-29"))
            self.addCleanup(state.db.close)
            state.db.execute("UPDATE partitions SET status='done' WHERE mode='unfiltered'")
            state.db.commit()
            data = {"results": [{"id": 1}], "total_pages": 999, "total_results": 19980}
            state.save_pages([(state.next_partition("tv"), data)])
            part = state.next_partition("tv")
            self.assertEqual((part["pages"], part["limited"]), (500, 1))
            state.db.execute("UPDATE partitions SET page=499 WHERE status='pending'")
            state.db.commit()
            command = animation.Command(stdout=io.StringIO())
            command.state, command.config = state, {**state.meta("config"), "sort": "popularity.desc", "min_votes": 0, "exclude_anime": False}
            command.secrets = []
            command.api = Mock()
            command.api.get.return_value = data
            self.assertTrue(command.discover_round())
            self.assertEqual(command.api.get.call_args.args[1]["page"], 500)
            self.assertEqual(command.api.get.call_args.args[1]["first_air_date.gte"], "2020-02-29")
            self.assertFalse(command.discover_round())
            self.assertEqual(command.api.get.call_count, 1)
            self.assertEqual(state.statistics()["coverage_limited_partitions"], 1)

    def test_unfiltered_500th_page_continues_into_dated_discovery(self):
        self.state.db.execute("UPDATE partitions SET status='done' WHERE media_type='tv'")
        self.state.db.execute("UPDATE partitions SET page=499,pages=500 WHERE media_type='movie' AND mode='unfiltered'")
        self.state.db.commit()
        command = animation.Command(stdout=io.StringIO())
        command.state, command.config = self.state, {**self.state.meta("config"), "sources": ["movie"], "sort": "popularity.desc", "min_votes": 0, "exclude_anime": False}
        command.secrets = []
        command.api = Mock()
        command.api.get.return_value = {"results": [{"id": 1}], "total_pages": 501}
        self.assertTrue(command.discover_round())
        self.assertEqual(command.api.get.call_args.args[1]["page"], 500)
        self.assertTrue(command.discover_round())
        parameters = command.api.get.call_args.args[1]
        self.assertEqual(parameters["page"], 1)
        self.assertEqual(parameters["primary_release_date.gte"], "2020-02-28")
        self.assertEqual(parameters["primary_release_date.lte"], "2020-03-01")
        self.assertIsNotNone(self.state.next_partition("movie"))

    def test_invalid_options_and_unsupported_database_do_not_create_state(self):
        command = animation.Command()
        options = vars(command.create_parser("manage.py", "import_animation").parse_args([]))
        for values in [{"target_new": 15001}, {"target_new": 0}, {"max_candidates": -1},
                       {"date_from": "2020-02-30"}, {"languages": "ru"}, {"tmdb_delay": 0}]:
            with self.subTest(values=values), self.assertRaises(CommandError):
                command.configuration({**options, **values}, None)
        with tempfile.TemporaryDirectory() as directory, patch.object(animation, "connection") as database:
            database.vendor = "sqlite"
            with self.assertRaisesMessage(CommandError, "requires PostgreSQL"):
                call_command("import_animation", state_dir=directory, stdout=io.StringIO())
            self.assertFalse(list(Path(directory).iterdir()))

    def test_old_movie_and_anime_manifests_rejected_without_writes(self):
        for cls in [popular.State, anime.AnimeState]:
            with tempfile.TemporaryDirectory() as directory:
                old = cls(directory)
                old.set_meta("config", {"importer": "anime-v1"} if cls is anime.AnimeState else {"version": 1})
                old.db.close()
                path = Path(directory) / "state.sqlite3"
                before = path.read_bytes()
                with self.assertRaises(CommandError):
                    call_command("import_animation", state_dir=directory, stdout=io.StringIO())
                self.assertEqual(path.read_bytes(), before)
                self.assertFalse((Path(directory) / "run.lock").exists())

    def test_dry_run_finish_never_marks_apply_queue_terminal(self):
        self.state.save_pages([(self.state.next_partition("movie"), {"results": [{"id": 1}], "total_pages": 1})])
        row = self.state.candidates(1)[0]
        self.state.finish(row, "would_create", dry_run_id="test")
        self.assertEqual(self.state.candidates(1)[0]["status"], "pending")
        self.assertFalse(self.state.candidates(1, dry_run_id="test"))
        self.state.report({"status": "source_exhausted"})
        self.assertIn("dry_reason_code", (Path(self.temp.name) / "import_report.csv").read_text(encoding="utf-8-sig"))

    def test_keywords_are_optional_without_exclusion_but_partial_error_is_not_an_empty_list(self):
        item = detail("tv", 1)
        item["keywords"] = None
        animation.validate_animation(item, "tv", 1)
        with self.assertRaisesMessage(CommandError, "unavailable"):
            animation.validate_animation(item, "tv", 1, exclude_anime=True)


class ImportFixtures:
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "animation"
        self.output = io.StringIO()
        FixtureAPI.items = {(media, 1): detail(media, 1) for media in ("movie", "tv")}
        FixtureAPI.documents = {
            "Q1001": entity("Q1001", P31=["Q20650540"], P4947=["1"], P345=["tt1001"], P725=["Q900"]),
            "Q2001": entity("Q2001", P31=["Q1259759"], P4983=["1"], P345=["tt2001"]),
            "Q20650540": entity("Q20650540", P279=["Q11424"]),
            "Q1259759": entity("Q1259759", P279=["Q5398426"]),
            "Q24862": entity("Q24862", P279=["Q11424"]),
            "Q900": entity("Q900"),
        }
        FixtureAPI.bindings, FixtureAPI.requests = [], []
        FixtureAPI.require_outside_atomic = False

    def run_import(self, **options):
        with patch.object(animation, "AnimeAPI", FixtureAPI), patch.dict("os.environ", {"TMDB_READ_TOKEN": "fixture-secret", "TMDB_API_KEY": ""}):
            call_command("import_animation", state_dir=str(options.pop("directory", self.directory)),
                         stdout=self.output, **options)

    def rows(self):
        with sqlite3.connect(self.directory / "state.sqlite3") as db:
            db.row_factory = sqlite3.Row
            return db.execute("SELECT * FROM manifest ORDER BY position").fetchall()

    def summary(self):
        return json.loads((self.directory / "summary.json").read_text())

    def add_movie(self, number):
        FixtureAPI.items[("movie", number)] = detail("movie", number)
        qid = f"Q{1000 + number}"
        FixtureAPI.documents[qid] = entity(qid, P31=["Q20650540"], P4947=[str(number)], P345=[f"tt{1000 + number}"])


@skipUnless(connection.vendor == "postgresql", "Animation campaigns require PostgreSQL")
class ImportAnimationTests(ImportFixtures, TestCase):
    def test_feature_short_and_whole_miniseries_preserve_specific_types_and_voice_cast(self):
        self.add_movie(2)
        FixtureAPI.documents["Q1002"]["claims"]["P31"] = [statement({"id": "Q24862"})]
        self.run_import()
        self.assertEqual(Movie.objects.count(), 3)
        self.assertEqual(Movie.objects.get(wikidata_id="Q1002").type_of_work.wikidata_id, "Q24862")
        self.assertEqual(Movie.objects.get(wikidata_id="Q2001").type_of_work.wikidata_id, "Q1259759")
        self.assertEqual(Movie.objects.get(wikidata_id="Q1001").actors.get().wikidata_id, "Q900")
        self.assertEqual(self.summary()["status"], "source_exhausted")
        self.assertEqual(self.summary()["created_in_campaign"], 3)
        self.assertEqual(self.summary()["shortfall"], 14997)
        for movie in Movie.objects.all():
            self.assertEqual(movie.translations.count(), 6)

    def test_adult_video_non_animation_parts_collectives_and_conflicting_formats_are_skipped(self):
        for number in range(2, 6):
            self.add_movie(number)
        FixtureAPI.items[("movie", 1)]["genres"] = [{"id": 18}]
        FixtureAPI.items[("movie", 2)]["adult"] = True
        FixtureAPI.items[("movie", 3)]["video"] = True
        for number, forbidden in [(4, "Q24856"), (5, "Q95074")]:
            FixtureAPI.documents[f"Q{1000 + number}"]["claims"]["P31"].append(statement({"id": forbidden}))
        for number, work_type in [(1, "Q3464665"), (2, "Q21191270"), (3, "Q11424")]:
            FixtureAPI.items[("tv", number)] = detail("tv", number)
            FixtureAPI.documents[f"Q{2000 + number}"] = entity(f"Q{2000 + number}", P31=[work_type], P4983=[str(number)])
        self.run_import()
        self.assertEqual(Movie.objects.count(), 0)
        self.assertEqual(TypeOfWork.objects.count(), 0)
        counts = self.summary()["campaign_state"]["skips_by_reason"]
        self.assertEqual(counts, {"adult_video": 2, "invalid_format": 5, "non_animation": 1})

    def test_keyword_wrappers_include_by_default_and_exact_optional_exclusion(self):
        for (media, _), item in FixtureAPI.items.items():
            item["keywords"]["keywords" if media == "movie" else "results"] = [{"id": 210024}]
            item["original_language"] = "ja"
        self.run_import()
        self.assertEqual(Movie.objects.count(), 2)
        self.run_import(exclude_anime=True, directory=Path(self.temp.name) / "excluded")
        self.assertEqual(Movie.objects.count(), 2)
        report = json.loads((Path(self.temp.name) / "excluded" / "summary.json").read_text())
        self.assertEqual(report["campaign_state"]["skips_by_reason"], {"excluded_anime": 2})
        for (media, _), item in FixtureAPI.items.items():
            item["keywords"]["keywords" if media == "movie" else "results"] = [{"id": 222243}]
        self.run_import(exclude_anime=True, directory=Path(self.temp.name) / "not-exact")
        self.assertEqual(AnimationImportReceipt.objects.count(), 4)
        self.assertEqual(Movie.objects.count(), 2)

    def test_target_counts_new_only_and_resume_preserves_rest_of_page(self):
        Movie.objects.create(wikidata_id="Q1001", name="Existing anime")
        for number in [2, 3]:
            self.add_movie(number)
        self.run_import(target_new=1)
        self.assertEqual(self.summary()["status"], "target_reached")
        self.assertEqual(self.summary()["created_in_campaign"], 1)
        self.assertEqual([row["status"] for row in self.rows()], ["updated", "created", "pending", "pending"])
        before = Movie.objects.get(wikidata_id="Q2001").last_synced_at
        self.run_import(target_new=3)
        self.assertEqual(self.summary()["created_in_campaign"], 3)
        self.assertEqual(Movie.objects.count(), 4)
        self.assertEqual(Movie.objects.get(wikidata_id="Q2001").last_synced_at, before)
        self.assertEqual(AnimationImportReceipt.objects.filter(outcome="created").count(), 3)

    def test_candidate_budget_stops_without_exhausting_and_same_command_continues_other_source(self):
        self.run_import(max_candidates=1)
        self.assertEqual(self.summary()["status"], "candidate_budget_reached")
        self.assertEqual(Movie.objects.count(), 1)
        self.run_import(max_candidates=1)
        self.assertEqual(Movie.objects.count(), 2)
        self.assertEqual(self.summary()["run"]["examined"], 1)
        self.assertEqual(self.summary()["created_in_campaign"], 2)
        self.assertEqual([row["media_type"] for row in self.rows()], ["movie", "tv"])

    def test_retry_at_reached_target_preserves_terminal_skip_statistics(self):
        FixtureAPI.items[("movie", 1)]["genres"] = [{"id": 18}]
        self.run_import(target_new=1)
        self.run_import(target_new=1, retry_skipped=True)
        self.assertEqual(self.summary()["status"], "target_reached")
        self.assertEqual(self.summary()["campaign_state"]["skips_by_reason"], {"non_animation": 1})
        self.assertEqual(self.summary()["run"]["processed"], 0)

    def test_dry_run_has_no_django_or_index_writes_and_apply_uses_same_candidates(self):
        with patch.object(animation, "refresh_movie_documents") as index:
            self.run_import(dry_run=True, max_candidates=40)
            index.assert_not_called()
        for model in [Movie, TypeOfWork, Person, AnimationImportReceipt, GlobalSearchIndex]:
            self.assertEqual(model.objects.count(), 0)
        self.assertEqual([row["status"] for row in self.rows()], ["pending", "pending"])
        self.assertEqual(self.summary()["campaign_state"]["dry_run"], {"would_create": 2})
        self.assertEqual(self.summary()["created_in_campaign"], 0)
        self.run_import()
        self.assertEqual(Movie.objects.count(), 2)
        self.assertEqual(GlobalSearchIndex.objects.count(), 2)
        self.run_import(refresh_cache=True)
        self.assertEqual(self.summary()["created_in_campaign"], 2)
        self.assertEqual(Movie.objects.count(), 2)

    def test_no_wikidata_and_ambiguous_mapping_have_distinct_reasons_and_can_be_retried(self):
        FixtureAPI.items.pop(("tv", 1))
        self.add_movie(2)
        for item in FixtureAPI.items.values():
            item["external_ids"] = {}
        FixtureAPI.bindings = [
            {"item": {"value": "http://www.wikidata.org/entity/" + qid},
             "source": {"value": "tmdb"}, "identifier": {"value": "2"}}
            for qid in ["Q1002", "Q9999"]
        ]
        self.run_import(media_type="movie")
        self.assertEqual(self.summary()["campaign_state"]["skips_by_reason"], {"ambiguous_identity": 1, "no_wikidata_match": 1})
        self.assertEqual(Movie.objects.count(), 0)
        self.run_import(media_type="movie", retry_skipped=True, dry_run=True)
        self.assertEqual([row["status"] for row in self.rows()], ["skipped", "skipped"])
        for pair in FixtureAPI.items:
            FixtureAPI.items[pair] = detail(*pair)
        self.run_import(media_type="movie", retry_skipped=True, refresh_cache=True)
        self.assertEqual(Movie.objects.count(), 2)

    def test_canonical_redirect_and_two_candidates_for_one_work_never_create_duplicates(self):
        FixtureAPI.items.pop(("tv", 1))
        self.add_movie(2)
        FixtureAPI.items[("movie", 1)]["external_ids"]["wikidata_id"] = "Q9991"
        FixtureAPI.documents["Q9991"] = copy.deepcopy(FixtureAPI.documents["Q1001"])
        for key in ["Q9991", "Q1001"]:
            FixtureAPI.documents[key]["claims"].pop("P4947")
        FixtureAPI.items[("movie", 2)]["external_ids"] = {"wikidata_id": "Q1001", "imdb_id": "tt1001"}
        self.run_import(media_type="movie", dry_run=True)
        self.assertEqual(self.summary()["campaign_state"]["dry_run"], {"would_create": 1, "would_duplicate": 1})
        self.run_import(media_type="movie")
        self.assertEqual(Movie.objects.count(), 1)
        self.assertEqual(Movie.objects.get().wikidata_id, "Q1001")
        self.assertEqual(self.summary()["created_in_campaign"], 1)
        self.assertEqual([row["status"] for row in self.rows()], ["created", "existing"])

    def test_manual_fields_translations_relations_and_user_ratings_are_preserved(self):
        manual_type = TypeOfWork.objects.create(wikidata_id="Q777")
        genre = Genre.objects.create(wikidata_id="Q778")
        movie = Movie.objects.create(wikidata_id="Q1001", imdb_id="tt1001", name="Manual title", description="Manual text",
                                     year=1990, rate="9.2", cover="movie_covers/manual.jpg", type_of_work=manual_type)
        popular.fill_translations(movie, {"ru": {"wikidata_name": "Ручное название"}})
        movie.genres.add(genre)
        user = get_user_model().objects.create_user(username="animation-reviewer", email="reviewer@example.com")
        review = Review.objects.create(user=user, movie=movie, rating=8, text="Keep review")
        vote = ReviewVote.objects.create(user=user, review=review, value=1)
        FixtureAPI.items.pop(("tv", 1))
        self.run_import()
        movie.refresh_from_db(); review.refresh_from_db()
        self.assertEqual((movie.name, movie.description, movie.year, str(movie.rate)), ("Manual title", "Manual text", 1990, "9.2"))
        self.assertEqual(movie.type_of_work_id, manual_type.pk)
        self.assertEqual(movie.cover.name, "movie_covers/manual.jpg")
        self.assertEqual(movie.translations.get(language_code="ru").wikidata_name, "Ручное название")
        self.assertEqual(movie.genres.get().pk, genre.pk)
        self.assertEqual((review.text, review.rating), ("Keep review", 8))
        self.assertEqual(ReviewVote.objects.get(pk=vote.pk).value, 1)
        self.assertEqual(self.summary()["created_in_campaign"], 0)
        self.assertEqual(self.rows()[0]["status"], "updated")
        self.run_import(directory=Path(self.temp.name) / "another-campaign")
        self.assertEqual(AnimationImportReceipt.objects.filter(outcome="existing").count(), 1)

    def test_same_title_year_without_matching_ids_is_never_merged(self):
        Movie.objects.create(name="Animated movie 1", year=2001)
        FixtureAPI.items.pop(("tv", 1))
        self.run_import()
        self.assertEqual(Movie.objects.count(), 1)
        self.assertEqual(self.rows()[0]["reason_code"], "identity_conflict")

    def test_missing_poster_date_and_translations_are_not_fabricated(self):
        FixtureAPI.items.pop(("movie", 1))
        item = FixtureAPI.items[("tv", 1)]
        item.update(first_air_date="", poster_path=None, translations={"translations": []})
        data = FixtureAPI.documents["Q2001"]
        data["labels"] = {"en": {"value": "English TV title"}}
        data["claims"]["P580"] = [statement({"time": "+1998-01-01T00:00:00Z"})]
        self.run_import()
        movie = Movie.objects.get()
        self.assertEqual(movie.year, 1998)
        self.assertEqual(movie.cover_url, "")
        self.assertEqual(set(movie.translations.values_list("language_code", flat=True)), {"en"})

    def test_missing_wikidata_entity_is_reported_as_no_match_not_a_temporary_network_error(self):
        FixtureAPI.documents["Q1001"] = {"id": "Q1001", "missing": ""}
        self.run_import()
        self.assertEqual(self.summary()["campaign_state"]["skips_by_reason"], {"no_wikidata_match": 1})
        self.assertEqual(Movie.objects.count(), 1)

    def test_all_six_translations_are_searchable_without_rebuilding_other_documents(self):
        other = Movie.objects.create(name="unrelated original")
        refresh_movie_documents([other.pk])
        old = GlobalSearchIndex.objects.get(object_id=other.pk)
        old_vector = old.search_vector
        names = {"en": "quasaranimation", "ru": "северноесияние", "uk": "мандрівкавеселка", "kk": "сиқырлыорман", "es": "maravillaanimada", "de": "zauberzeichentrick"}
        for row in FixtureAPI.items[("movie", 1)]["translations"]["translations"]:
            row["data"]["title"] = names[row["iso_639_1"]]
        self.run_import()
        movie = Movie.objects.get(wikidata_id="Q1001")
        for language, text in names.items():
            with self.subTest(language=language):
                response = self.client.get(reverse("movies:search_results_api"), {"query": text})
                self.assertEqual(response.status_code, 200)
                self.assertIn(movie.pk, [result["id"] for result in response.json()["results"] if result["type"] == "movie"])
        old.refresh_from_db()
        self.assertEqual(old.search_vector, old_vector)
        self.assertFalse(AnimationImportReceipt.objects.filter(indexed=False).exists())

    def test_configuration_mismatch_is_rejected_before_writing_state(self):
        self.run_import(max_candidates=1)
        path = self.directory / "state.sqlite3"
        before = path.read_bytes()
        for options in [{"min_votes": 50}, {"exclude_anime": True}, {"media_type": "movie"}, {"date_from": "2020-01-01"}]:
            with self.subTest(options=options), self.assertRaises(CommandError):
                self.run_import(**options)
            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(saved_config(self.directory)["date_from"], "0001-01-01")

    def test_targeted_index_failure_rolls_back_affected_documents(self):
        obj = Movie.objects.create(name="Keep existing search vector")
        refresh_movie_documents([obj.pk])
        before = list(GlobalSearchIndex.objects.values())
        with patch("movies.services.search_index.index_new_movies", side_effect=RuntimeError("build failed")):
            with self.assertRaises(RuntimeError):
                refresh_movie_documents([obj.pk])
        self.assertEqual(list(GlobalSearchIndex.objects.values()), before)

    def test_movie_command_defaults_and_public_interface_remain_usable(self):
        class LegacyAPI(FixtureAPI):
            def details(self, tmdb_id):
                return super().details("movie", tmdb_id)

            def get(self, url, params=None):
                if url.endswith("/discover/movie"):
                    assert params["vote_count.gte"] == 50
                    return {"results": [{"id": 1}], "total_pages": 1}
                return super().get(url, params)

        with patch.object(popular, "API", LegacyAPI), patch.dict("os.environ", {"TMDB_READ_TOKEN": "fixture"}):
            call_command("import_popular_movies", limit=1, skip_backfill=True,
                         state_dir=str(Path(self.temp.name) / "old-default"), stdout=self.output)
            self.assertEqual(Movie.objects.count(), 0)  # Existing default excludes Animation.
            call_command("import_popular_movies", limit=1, skip_backfill=True, without_genres="",
                         state_dir=str(Path(self.temp.name) / "old-including-animation"), stdout=self.output)
        self.assertEqual(Movie.objects.count(), 1)
        self.assertEqual(AnimationImportReceipt.objects.count(), 0)

    def test_failed_index_keeps_previous_documents_and_is_recovered_even_at_target(self):
        other = Movie.objects.create(name="previous document")
        refresh_movie_documents([other.pk])
        with patch.object(animation, "refresh_movie_documents", side_effect=RuntimeError("index fixture")):
            with self.assertRaises(CommandError):
                self.run_import(target_new=1)
        self.assertEqual(Movie.objects.count(), 2)
        self.assertTrue(GlobalSearchIndex.objects.filter(object_id=other.pk).exists())
        self.assertEqual(self.summary()["status"], "failed")
        self.assertEqual(self.summary()["pending_index_receipts"], 1)
        self.run_import(target_new=1)
        self.assertEqual(self.summary()["status"], "target_reached")
        self.assertEqual(self.summary()["pending_index_receipts"], 0)

    def test_http_failure_is_not_a_permanent_no_match_and_credentials_are_redacted(self):
        with patch.object(FixtureAPI, "resolve", side_effect=CommandError("fixture-secret API unavailable")):
            with self.assertRaises(CommandError) as failure:
                self.run_import()
        self.assertNotIn("fixture-secret", str(failure.exception))
        self.assertNotIn("fixture-secret", self.output.getvalue())
        self.assertEqual([row["status"] for row in self.rows()], ["pending", "pending"])
        self.assertEqual(self.summary()["campaign_state"]["failed_runs"], 1)
        self.run_import()
        self.assertEqual(Movie.objects.count(), 2)


@skipUnless(connection.vendor == "postgresql", "Receipt and cross-import locks require PostgreSQL")
class AnimationCommitAndLockTests(ImportFixtures, TransactionTestCase):
    def test_crash_between_django_commit_and_sqlite_finish_recovers_exact_count(self):
        FixtureAPI.require_outside_atomic = True
        original = AnimationState.finish

        def fail_after_commit(state, row, status, **kwargs):
            if status == "created":
                self.assertFalse(connection.in_atomic_block)
                raise RuntimeError("Simulated process death after Django commit")
            return original(state, row, status, **kwargs)

        with patch.object(AnimationState, "finish", fail_after_commit):
            with self.assertRaises(CommandError):
                self.run_import(target_new=1)
        self.assertEqual(Movie.objects.count(), 1)
        self.assertEqual(AnimationImportReceipt.objects.filter(outcome="created").count(), 1)
        self.assertEqual(self.summary()["run"]["created"], 1)
        self.assertEqual(self.rows()[0]["status"], "pending")
        self.run_import(target_new=2)
        self.assertEqual(Movie.objects.count(), 2)
        self.assertEqual(self.summary()["created_in_campaign"], 2)
        self.assertEqual([row["status"] for row in self.rows()], ["created", "created"])
        self.assertEqual(self.summary()["run"]["created"], 1)

    def test_sigterm_rolls_back_current_object_then_resume_and_sigint_exit_code(self):
        original = popular.relation_data
        calls = 0

        def stop_second(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                signal.raise_signal(signal.SIGTERM)
            return original(*args)

        with patch.object(popular, "relation_data", stop_second):
            with self.assertRaises(CommandError) as failure:
                self.run_import()
        self.assertEqual(failure.exception.returncode, 143)
        self.assertEqual(Movie.objects.count(), 1)
        self.assertEqual(AnimationImportReceipt.objects.count(), 1)
        self.assertEqual(self.summary()["status"], "interrupted")
        self.run_import()
        self.assertEqual(Movie.objects.count(), 2)
        with patch.object(FixtureAPI, "get", side_effect=KeyboardInterrupt):
            with self.assertRaises(CommandError) as failure:
                self.run_import(directory=Path(self.temp.name) / "interrupt")
        self.assertEqual(failure.exception.returncode, 130)

    def test_shared_lock_rejects_other_importer_or_state_dir_without_waiting(self):
        parameters = connection.get_connection_params()
        parameters["autocommit"] = True
        second = psycopg.connect(**parameters)
        self.addCleanup(second.close)
        with second.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [704913204817])
            self.assertTrue(cursor.fetchone()[0])
            try:
                with self.assertRaisesMessage(CommandError, "Другой импорт RAFS"):
                    self.run_import()
                with self.assertRaises(CommandError):
                    with popular.database_lock():
                        self.fail("Shared lock did not protect the old importer")
            finally:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [704913204817])
        with popular.run_lock(self.directory):
            with self.assertRaises(CommandError):
                self.run_import()
        self.run_import()
        self.assertEqual(Movie.objects.count(), 2)


class AnimationHTTPTests(SimpleTestCase):
    def test_shared_429_5xx_cache_and_maxlag_are_used_without_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            state = AnimationState(directory, config())
            self.addCleanup(state.db.close)
            api = anime.AnimeAPI(state, "", "fixture-secret", LANGUAGES, lambda _: None,
                                 {"tmdb": .6, "wikidata": 1, "sparql": 5}, maxlag_wait=0)
            self.addCleanup(api.session.close)
            responses = [Mock(status_code=429, headers={"Retry-After": "40"}), Mock(status_code=503, headers={})]
            success = Mock(status_code=200, headers={}); success.json.return_value = {"id": 1}
            with patch.object(api.session, "get", side_effect=[*responses, success]) as get, \
                    patch.object(popular.time, "sleep") as sleep, patch.object(popular.random, "uniform", return_value=0):
                self.assertEqual(api.details("movie", 1), {"id": 1})
                self.assertTrue(any(call.args[0] > 39 for call in sleep.call_args_list))
                self.assertEqual(api.details("movie", 1), {"id": 1})
                self.assertEqual(get.call_count, 3)
            lag = Mock(status_code=200, headers={}); lag.json.return_value = {"error": {"code": "maxlag", "lag": 8}}
            with patch.object(api.session, "get", return_value=lag) as get:
                with self.assertRaisesMessage(CommandError, "maxlag"):
                    api.entities(["Q101"], claims=True)
                self.assertEqual(get.call_count, 1)
                self.assertEqual(get.call_args.kwargs["params"]["maxlag"], 5)
            self.assertNotIn("fixture-secret", " ".join(state.db.iterdump()))
