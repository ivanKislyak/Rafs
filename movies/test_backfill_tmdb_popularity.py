"""Snapshot/mapping/batch checks on Django's isolated test database; no live API."""

import gzip
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from io import StringIO
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

import requests
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.search import SearchVector, SearchQuery
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection
from django.db.models import Value
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from accounts.models import User
from movies.management.commands.backfill_tmdb_popularity import http_key
from movies.management.commands.import_popular_movies import API, State, TMDB
from movies.management.commands.import_anime import AnimeState
from movies.models import GlobalSearchIndex, Movie
from movies.services.search_index import index_new_movies


MODULE = "movies.management.commands.backfill_tmdb_popularity"


class PopularityBackfillTests(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="rafs-popularity-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.movie = Movie.objects.create(name="Existing film", wikidata_id="Q100", imdb_id="tt100", tmdb_popularity=7)
        self.tv = Movie.objects.create(name="Existing TV", wikidata_id="Q200", imdb_id="tt200", tmdb_popularity=8)
        self.ct = ContentType.objects.get_for_model(Movie)
        self.document = GlobalSearchIndex.objects.create(content_type=self.ct, object_id=self.movie.pk, tmdb_popularity=9)
        self.tv_document = GlobalSearchIndex.objects.create(content_type=self.ct, object_id=self.tv.pk, tmdb_popularity=9)
        self.paths = {media: self.root / f"{prefix}_11_08_2026.json.gz" for media, prefix in (("movie", "movie_ids"), ("tv", "tv_series_ids"))}
        self.export("movie", [{"id": 10, "popularity": 42.5}])
        self.export("tv", [{"id": 10, "popularity": 13.25}])
        # Exercise the actual legacy and anime state writers, including cache hashes.
        self.legacy = State(self.root / "popular")
        self.anime = AnimeState(self.root / "anime")
        self.addCleanup(self.legacy.db.close)
        self.addCleanup(self.anime.db.close)
        self.legacy.db.execute("INSERT INTO manifest(tmdb_id) VALUES (10)")
        self.legacy.db.commit()
        self.legacy.mark(10, "created", self.movie.pk)
        self.cache_details(self.legacy, self.movie, "movie", 10)
        self.anime.db.execute("INSERT INTO manifest(media_type,tmdb_id) VALUES ('tv',10)")
        self.anime.db.commit()
        self.anime.mark("tv", 10, "updated", self.tv.pk)
        self.cache_details(self.anime, self.tv, "tv", 10)
        self.states = [self.legacy.directory / "state.sqlite3", self.anime.directory / "state.sqlite3"]

    def export(self, media, rows):
        with gzip.open(self.paths[media], "wt", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row) + "\n")

    @staticmethod
    def cache_details(state, movie, media, tmdb_id, **overrides):
        append = "external_ids,translations" if media == "movie" else "external_ids,translations,keywords"
        data = {"id": tmdb_id, "external_ids": {"wikidata_id": movie.wikidata_id, "imdb_id": movie.imdb_id}, **overrides}
        state.put(http_key(f"{TMDB}/{media}/{tmdb_id}", {"language": "en-US", "append_to_response": append}), data)

    def run_command(self, **kwargs):
        output = StringIO()
        call_command("backfill_tmdb_popularity", movie_export=str(self.paths["movie"]), tv_export=str(self.paths["tv"]),
                     import_state=[str(path) for path in self.states], stdout=output, **kwargs)
        return output.getvalue()

    @staticmethod
    def values():
        return (list(Movie.objects.order_by("pk").values()), list(GlobalSearchIndex.objects.order_by("pk").values()))

    def test_pair_identity_dry_run_idempotence_and_read_only_states(self):
        before = self.values()
        hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in self.states]
        with patch(f"{MODULE}.API") as api, patch(f"{MODULE}.database_lock") as lock, CaptureQueriesContext(connection) as queries:
            output = self.run_command(dry_run=True)
            api.assert_not_called()
            lock.assert_not_called()
        self.assertFalse(any(re.match(r"\s*(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b", query["sql"], re.I) for query in queries))
        self.assertIn('"updated_movies": 2', output)
        self.assertEqual(self.values(), before)
        self.run_command()
        self.movie.refresh_from_db(); self.tv.refresh_from_db()
        self.assertEqual((self.movie.tmdb_popularity, self.tv.tmdb_popularity), (42.5, 13.25))
        self.document.refresh_from_db(); self.tv_document.refresh_from_db()
        self.assertEqual((self.document.tmdb_popularity, self.tv_document.tmdb_popularity), (42.5, 13.25))
        after = self.values()
        output = self.run_command()
        self.assertIn('"updated_movies": 0', output)
        self.assertIn('"updated_documents": 0', output)
        self.assertEqual(self.values(), after)
        self.assertEqual([hashlib.sha256(path.read_bytes()).hexdigest() for path in self.states], hashes)

    def test_all_exports_are_validated_before_any_write(self):
        before = self.values()
        invalid = [[], [{"id": 10}], [{"id": 10, "popularity": -1}], [{"id": 10, "popularity": float("nan")}],
                   [{"id": 10, "popularity": float("inf")}], [{"id": 10, "popularity": True}],
                   [{"id": True, "popularity": 1}], [{"id": 10, "popularity": "2"}],
                   [{"id": 10, "popularity": 1}] * 2]
        for rows in invalid:
            with self.subTest(rows=rows):
                self.export("tv", rows)
                with self.assertRaises(CommandError):
                    self.run_command(batch_size=1)
                self.assertEqual(self.values(), before)
        self.paths["tv"].write_bytes(b"not gzip")
        with self.assertRaises(CommandError):
            self.run_command()
        self.export("tv", [{"id": 10, "popularity": 1}])
        data = self.paths["tv"].read_bytes()
        self.paths["tv"].write_bytes(data[:-6])
        with self.assertRaises(CommandError):
            self.run_command()
        self.paths["tv"].unlink()
        with self.assertRaises(CommandError):
            self.run_command()
        self.assertEqual(self.values(), before)

    def test_snapshot_dates_must_match(self):
        wrong = self.paths["tv"].with_name("tv_series_ids_11_09_2026.json.gz")
        self.paths["tv"].rename(wrong)
        self.paths["tv"] = wrong
        with self.assertRaisesMessage(CommandError, "same daily snapshot"):
            self.run_command()

    def test_real_importer_detail_cache_keys_are_supported(self):
        self.legacy.db.execute("DELETE FROM cache")
        self.legacy.db.commit()
        api = API(self.legacy, "test-token", "", ["en"], lambda _: None,
                  {"tmdb": .6, "wikidata": 1, "sparql": 5})
        self.addCleanup(api.session.close)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({"id": 10, "imdb_id": self.movie.imdb_id}).encode()
        with patch.object(api.session, "get", return_value=response):
            api.details(10)
        self.run_command(limit=1)
        self.movie.refresh_from_db(); self.assertEqual(self.movie.tmdb_popularity, 42.5)

    def test_existing_document_is_repaired_even_if_movie_value_is_correct(self):
        Movie.objects.filter(pk=self.movie.pk).update(tmdb_popularity=42.5)
        self.tv_document.delete()
        output = self.run_command()
        self.assertIn('"updated_movies": 1', output)
        self.assertIn('"missing_documents": 1', output)
        self.document.refresh_from_db()
        self.assertEqual(self.document.tmdb_popularity, 42.5)
        self.assertFalse(GlobalSearchIndex.objects.filter(pk=self.tv_document.pk).exists())

    def test_missing_snapshot_id_is_confirmed_zero(self):
        self.export("movie", [{"id": 999, "popularity": 1}])
        output = self.run_command()
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.tmdb_popularity, 0)
        self.assertIn('"zero_missing_export": 1', output)
        self.assertIn('"confirmed_zeros": 1', output)

    def test_final_report_distinguishes_updates_zeros_conflicts_and_unprocessed(self):
        self.export("tv", [{"id": 99, "popularity": 1}])
        self.tv_document.delete()
        Movie.objects.create(name="Unmapped", wikidata_id="Q300", tmdb_popularity=55)
        conflict = Movie.objects.create(name="Conflicting", wikidata_id="Q400", tmdb_popularity=66)
        GlobalSearchIndex.objects.create(content_type=self.ct, object_id=conflict.pk, tmdb_popularity=66)
        self.legacy.db.execute("INSERT INTO manifest(tmdb_id,status,movie_pk) VALUES (11,'created',?)", (conflict.pk,))
        self.legacy.db.commit()
        self.cache_details(self.legacy, conflict, "movie", 11, external_ids={"wikidata_id": "Q999"})
        output = self.run_command()
        report = json.loads(output.strip().splitlines()[-1].split(": ", 1)[1])
        self.assertEqual({key: report[key] for key in ["viewed", "updated_movies", "updated_documents", "confirmed_zeros", "conflict", "unprocessed", "missing_documents"]},
                         {"viewed": 4, "updated_movies": 2, "updated_documents": 1, "confirmed_zeros": 1, "conflict": 1, "unprocessed": 2, "missing_documents": 2})

    def test_unconfirmed_pk_and_dry_only_imports_cannot_supply_mapping(self):
        for mode in ["no_cache", "pending", "skipped", "error"]:
            with self.subTest(mode=mode):
                self.legacy.db.execute("DELETE FROM cache")
                self.legacy.mark(10, "created" if mode == "no_cache" else mode, self.movie.pk)
                self.anime.mark("tv", 10, "pending", self.tv.pk, dry_run=True)
                before = self.movie.tmdb_popularity
                self.run_command()
                self.movie.refresh_from_db()
                self.assertEqual(self.movie.tmdb_popularity, before)

    def test_dry_status_does_not_turn_a_pending_candidate_into_evidence(self):
        self.anime.mark("tv", 10, "pending", self.tv.pk)
        self.anime.mark("tv", 10, "created", self.tv.pk, dry_run=True)
        self.run_command(after_pk=self.movie.pk)
        self.tv.refresh_from_db(); self.assertEqual(self.tv.tmdb_popularity, 8)

    def test_reused_pk_and_contradictory_identifiers_are_conflicts(self):
        self.cache_details(self.legacy, self.movie, "movie", 10, external_ids={"wikidata_id": "Q999", "imdb_id": self.movie.imdb_id})
        output = self.run_command()
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.tmdb_popularity, 7)
        self.assertIn('"conflict": 1', output)
        self.assertIn('"unprocessed": 1', output)

    def test_multiple_pairs_for_one_movie_are_not_averaged_or_guessed(self):
        self.anime.db.execute("INSERT INTO manifest(media_type,tmdb_id,status,movie_pk) VALUES ('movie',99,'existing',?)", (self.movie.pk,))
        self.anime.db.commit()
        self.cache_details(self.anime, self.movie, "movie", 99)
        output = self.run_command()
        self.movie.refresh_from_db(); self.assertEqual(self.movie.tmdb_popularity, 7)
        self.assertIn('"conflict": 1', output)

    def test_campaign_schema_uses_real_status_and_cached_identity(self):
        campaign = self.root / "campaign.sqlite3"
        with sqlite3.connect(campaign) as db:
            db.executescript("CREATE TABLE manifest(movie_pk INTEGER,media_type TEXT,tmdb_id INTEGER,status TEXT,wikidata_id TEXT,dry_status TEXT); CREATE TABLE cache(key TEXT PRIMARY KEY,value TEXT);")
            db.execute("INSERT INTO manifest VALUES (?,'movie',10,'existing','Q100','would_create')", (self.movie.pk,))
            key, value = self.legacy.db.execute("SELECT key,value FROM cache").fetchone()
            details = json.loads(value)
            details["external_ids"] = {}  # Canonical import result + its cached details.
            db.execute("INSERT INTO cache VALUES (?,?)", (key, json.dumps(details)))
        self.states = [campaign]
        self.run_command()
        self.movie.refresh_from_db(); self.assertEqual(self.movie.tmdb_popularity, 42.5)

    def test_a_tmdb_pair_claimed_by_different_movie_pks_is_a_conflict(self):
        self.anime.db.execute("INSERT INTO manifest(media_type,tmdb_id,status,movie_pk) VALUES ('movie',10,'existing',?)", (self.tv.pk,))
        self.anime.db.commit()
        self.cache_details(self.anime, self.tv, "movie", 10)
        output = self.run_command()
        self.movie.refresh_from_db(); self.tv.refresh_from_db()
        self.assertEqual((self.movie.tmdb_popularity, self.tv.tmdb_popularity), (7, 8))
        self.assertIn('"conflict": 2', output)

    def test_unresolved_missing_documents_are_counted_without_creating_them(self):
        self.states = []
        self.tv_document.delete()
        output = self.run_command()
        self.assertIn('"missing_mapping": 2', output)
        self.assertIn('"missing_documents": 1', output)
        self.assertIn('"unprocessed": 2', output)

    def test_identity_change_between_lookup_and_commit_is_retained(self):
        from movies.management.commands.backfill_tmdb_popularity import Command
        original = Command.write_batch
        def changed(resolved, content_type, dry_run, counts, scanned_ids):
            Movie.objects.filter(pk=self.movie.pk).update(imdb_id="tt999")
            return original(resolved, content_type, dry_run, counts, scanned_ids)
        with patch.object(Command, "write_batch", side_effect=changed):
            output = self.run_command()
        self.movie.refresh_from_db(); self.document.refresh_from_db()
        self.assertEqual((self.movie.tmdb_popularity, self.document.tmdb_popularity), (7, 9))
        self.assertIn('"concurrent_identity_change": 1', output)

    def test_malformed_state_fails_before_writes(self):
        bad = self.root / "bad.sqlite3"
        bad.write_bytes(b"broken")
        self.states.append(bad)
        before = self.values()
        with self.assertRaisesMessage(CommandError, "supported import state"):
            self.run_command()
        self.assertEqual(self.values(), before)

    def test_limit_and_resume_checkpoint(self):
        output = self.run_command(limit=1, batch_size=1)
        self.assertIn(f"Committed batch: last_pk={self.movie.pk}", output)
        self.tv.refresh_from_db(); self.assertEqual(self.tv.tmdb_popularity, 8)
        output = self.run_command(after_pk=self.movie.pk, batch_size=1)
        self.assertIn('"viewed": 1', output)
        self.tv.refresh_from_db(); self.assertEqual(self.tv.tmdb_popularity, 13.25)

    def test_search_update_failure_rolls_back_both_tables(self):
        from django.db.models.query import QuerySet
        before = self.values()
        original = QuerySet.bulk_update
        # Preserve the real Movie write; fail only when its paired search write starts.
        def fail_documents(queryset, *args, **kwargs):
            if queryset.model is GlobalSearchIndex:
                raise DatabaseError("isolated test failure")
            return original(queryset, *args, **kwargs)
        with patch("django.db.models.query.QuerySet.bulk_update", autospec=True, side_effect=fail_documents):
            with self.assertRaisesMessage(CommandError, "Batch rolled back"):
                self.run_command()
        self.assertEqual(self.values(), before)

    def test_previous_batch_survives_later_failure(self):
        from django.db.models.query import QuerySet
        original = QuerySet.bulk_update
        attempts = 0
        def fail_second(queryset, *args, **kwargs):
            nonlocal attempts
            if queryset.model is GlobalSearchIndex:
                attempts += 1
                if attempts == 2:
                    raise DatabaseError("second batch failure")
            return original(queryset, *args, **kwargs)
        with patch.object(QuerySet, "bulk_update", autospec=True, side_effect=fail_second):
            with self.assertRaisesMessage(CommandError, f"last committed pk={self.movie.pk}"):
                self.run_command(batch_size=1)
        self.movie.refresh_from_db(); self.tv.refresh_from_db()
        self.document.refresh_from_db(); self.tv_document.refresh_from_db()
        self.assertEqual((self.movie.tmdb_popularity, self.document.tmdb_popularity), (42.5, 42.5))
        self.assertEqual((self.tv.tmdb_popularity, self.tv_document.tmdb_popularity), (8, 9))

    @patch.dict(os.environ, {"TMDB_READ_TOKEN": "test-only-token"})
    def test_exact_find_and_external_id_validation(self):
        self.states = []
        with patch.object(API, "get", side_effect=[
            {"movie_results": [{"id": 10}], "tv_results": []},
            {"movie_results": [{"id": 10}], "tv_results": []},
            {"id": 10, "wikidata_id": "Q100", "imdb_id": "tt100"},
        ]) as get:
            self.run_command(resolve_missing=True, limit=1)
        self.movie.refresh_from_db(); self.assertEqual(self.movie.tmdb_popularity, 42.5)
        self.assertEqual(get.call_args_list[0].args[0], f"{TMDB}/find/tt100")
        self.assertEqual(get.call_args_list[1].args[1]["external_source"], "wikidata_id")

    @patch.dict(os.environ, {"TMDB_READ_TOKEN": "test-only-token"})
    def test_find_absence_vs_ambiguity_error_and_conflicting_external_ids(self):
        self.states = []
        empty = {"movie_results": [], "tv_results": []}
        for payloads, expected, reason in [
            ([empty, empty], 0, "confirmed_zeros"),
            ([{"movie_results": [{"id": 10}], "tv_results": [{"id": 10}]}, empty], 7, "conflict"),
            ([CommandError("tmdb: temporary network failure; retries exhausted")], 7, "source_error"),
            ([{}], 7, "source_error"),
            ([{"movie_results": [{"id": 10}], "tv_results": []}, empty, {"id": 10, "imdb_id": "tt999"}], 7, "conflict"),
        ]:
            with self.subTest(reason=reason, expected=expected):
                Movie.objects.filter(pk=self.movie.pk).update(tmdb_popularity=7)
                with patch.object(API, "get", side_effect=payloads):
                    output = self.run_command(resolve_missing=True, limit=1)
                self.movie.refresh_from_db(); self.assertEqual(self.movie.tmdb_popularity, expected)
                self.assertIn(f'"{reason}": 1', output)

    @patch.dict(os.environ, {"TMDB_READ_TOKEN": "test-only-token"})
    def test_real_shared_client_retries_429_5xx_and_timeout_without_zeroing(self):
        self.states = []
        for failure in [requests.Timeout(), 429, 503]:
            with self.subTest(failure=failure):
                response = requests.Response()
                if isinstance(failure, int):
                    response.status_code = failure
                    response.headers["Retry-After"] = "0"
                with patch("requests.Session.get", side_effect=failure if isinstance(failure, Exception) else None, return_value=response) as get, patch("time.sleep"), patch("random.uniform", return_value=0):
                    output = self.run_command(resolve_missing=True, limit=1)
                self.assertEqual(get.call_count, 6)
                self.movie.refresh_from_db(); self.assertEqual(self.movie.tmdb_popularity, 7)
                self.document.refresh_from_db(); self.assertEqual(self.document.tmdb_popularity, 9)
                self.assertIn('"source_error": 1', output)
                category = "source_network_error" if isinstance(failure, Exception) else "source_http_429" if failure == 429 else "source_http_5xx"
                self.assertIn(f'"{category}": 1', output)

    @patch.dict(os.environ, {"TMDB_READ_TOKEN": "test-only-token"})
    def test_fallback_network_is_outside_the_commands_write_transaction(self):
        from movies.management.commands.backfill_tmdb_popularity import Command
        self.states = []
        in_write = False
        original = Command.write_batch
        def write(*args):
            nonlocal in_write
            in_write = True
            try:
                return original(*args)
            finally:
                in_write = False
        def get(*args):
            self.assertFalse(in_write)
            # TestCase itself wraps tests in atomic(); no command savepoint yet.
            self.assertTrue(all(block._from_testcase for block in connection.atomic_blocks))
            return {"movie_results": [], "tv_results": []}
        with patch.object(Command, "write_batch", side_effect=write), patch.object(API, "get", side_effect=get):
            self.run_command(resolve_missing=True, limit=1)

    @skipUnless(connection.vendor == "postgresql", "Real vectors/advisory locks require PostgreSQL")
    def test_vectors_document_pks_other_types_and_new_index_documents(self):
        GlobalSearchIndex.objects.filter(pk=self.document.pk).update(search_vector=SearchVector("object_id"))
        GlobalSearchIndex.objects.filter(pk=self.tv_document.pk).update(search_vector=SearchVector("object_id"))
        other_type = ContentType.objects.get_for_model(User)
        other = GlobalSearchIndex.objects.create(content_type=other_type, object_id=self.movie.pk, tmdb_popularity=999, search_vector=SearchVector(Value("other")))
        before = list(GlobalSearchIndex.objects.order_by("pk").values_list("pk", "content_type_id", "object_id", "search_vector"))
        self.run_command()
        self.assertEqual(list(GlobalSearchIndex.objects.order_by("pk").values_list("pk", "content_type_id", "object_id", "search_vector")), before)
        other.refresh_from_db(); self.assertEqual(other.tmdb_popularity, 999)
        fresh = Movie.objects.create(name="New film", tmdb_popularity=123)
        index_new_movies(movie_ids=[fresh.pk])
        doc = GlobalSearchIndex.objects.get(content_type=self.ct, object_id=fresh.pk)
        self.assertEqual(doc.tmdb_popularity, 123)
        self.assertTrue(GlobalSearchIndex.objects.filter(pk=doc.pk, search_vector=SearchQuery("film", config="english")).exists())

    @skipUnless(connection.vendor == "postgresql", "Advisory lock contention requires PostgreSQL")
    def test_another_import_writer_rejects_apply(self):
        import psycopg
        other = psycopg.connect(**connection.get_connection_params())
        other.autocommit = True
        try:
            with other.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_lock(%s)", [704913204817])
            before = self.values()
            with self.assertRaisesMessage(CommandError, "Другой импорт"):
                self.run_command()
            self.assertEqual(self.values(), before)
        finally:
            other.close()
