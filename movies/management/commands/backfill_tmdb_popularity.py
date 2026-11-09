"""Fill popularity from a validated TMDB snapshot, without rebuilding search.

Written with AI assistance. Import manifests are evidence, not authoritative
Movie primary keys. All source preparation and HTTP happen outside DB writes.
"""

import gzip
import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
import zlib
from collections import Counter
from contextlib import ExitStack, closing, nullcontext
from datetime import datetime
from pathlib import Path

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, transaction

from movies.management.commands.import_popular_movies import (
    API, IMDB, QID, TMDB, clean, database_lock,
)
from movies.models import GlobalSearchIndex, Movie


def http_key(url, params):
    return "http:" + hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()


def positive_id(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value < 2**63


class SourceProblem(Exception):
    """Keep the previous value when source evidence cannot be trusted."""


class Snapshot:
    """Disk-backed, temporary lookup; never write to an importer's state."""

    def __init__(self, db):
        self.db = db
        db.executescript("""
            CREATE TABLE exports(media TEXT, id INTEGER, popularity REAL, PRIMARY KEY(media,id));
            CREATE TABLE links(movie_pk INTEGER, media TEXT, id INTEGER, qid TEXT, imdb TEXT, issue TEXT);
            CREATE INDEX links_movie ON links(movie_pk);
            CREATE INDEX links_pair ON links(media,id);
            CREATE TABLE cache(key TEXT PRIMARY KEY, value TEXT);
        """)

    def cached(self, key):
        row = self.db.execute("SELECT value FROM cache WHERE key=?", (key,)).fetchone()
        return (True, json.loads(row[0])) if row else (False, None)

    def put(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO cache VALUES (?,?)", (key, json.dumps(value)))
        self.db.commit()

    def exports(self, paths):
        dates = []
        for media, prefix in (("movie", "movie_ids"), ("tv", "tv_series_ids")):
            path = Path(paths[media])
            match = re.fullmatch(prefix + r"_(\d{2}_\d{2}_\d{4})\.json\.gz", path.name)
            if not match:
                raise CommandError(f"Expected {prefix}_MM_DD_YYYY.json.gz: {path}")
            try:
                dates.append(datetime.strptime(match[1], "%m_%d_%Y").date())
            except ValueError as error:
                raise CommandError(f"Invalid snapshot date: {path.name}") from error
        if dates[0] != dates[1]:
            raise CommandError("Movie and TV exports must belong to the same daily snapshot.")
        for media, filename in paths.items():
            line_number = 0
            try:
                with gzip.open(filename, "rt", encoding="utf-8") as stream, self.db:
                    for line_number, line in enumerate(stream, 1):
                        row = json.loads(line)
                        if not isinstance(row, dict) or not positive_id(row.get("id")):
                            raise ValueError("invalid ID")
                        value = row.get("popularity")
                        if isinstance(value, bool) or not isinstance(value, (int, float)):
                            raise ValueError("popularity must be numeric")
                        value = float(value)
                        if not math.isfinite(value) or value < 0:
                            raise ValueError("popularity must be finite and nonnegative")
                        self.db.execute("INSERT INTO exports VALUES (?,?,?)", (media, row["id"], value))
                    if not line_number:
                        raise ValueError("empty export")
            except (OSError, EOFError, UnicodeError, ValueError, OverflowError, zlib.error, sqlite3.IntegrityError) as error:
                raise CommandError(f"Invalid {media} export at line {line_number}: {type(error).__name__}. No Movie writes.") from error
        return dates[0].isoformat()

    def import_state(self, filename):
        path = Path(filename).resolve()
        try:
            with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as source:
                source.row_factory = sqlite3.Row
                source.execute("PRAGMA query_only=ON")
                columns = {row[1] for row in source.execute("PRAGMA table_info(manifest)")}
                if not {"tmdb_id", "movie_pk", "status"} <= columns:
                    raise ValueError("unsupported manifest")
                if not {"key", "value"} <= {row[1] for row in source.execute("PRAGMA table_info(cache)")}:
                    raise ValueError("unsupported cache")
                # A read transaction gives a consistent view of an active WAL manifest.
                source.execute("BEGIN")
                with self.db:
                    for row in source.execute("SELECT * FROM manifest WHERE status IN ('created','updated','existing') AND movie_pk IS NOT NULL"):
                        media = row["media_type"] if "media_type" in columns else "movie"
                        pk, tmdb_id = row["movie_pk"], row["tmdb_id"]
                        if media not in {"movie", "tv"} or not positive_id(pk) or not positive_id(tmdb_id):
                            raise ValueError("invalid imported identity")
                        canonical = clean(row["wikidata_id"]) if "wikidata_id" in columns else ""
                        # Both detail-cache layouts used by the existing importers.
                        found = False
                        for append in ("external_ids,translations", "external_ids,translations,keywords"):
                            key = http_key(f"{TMDB}/{media}/{tmdb_id}", {"language": "en-US", "append_to_response": append})
                            cached = source.execute("SELECT value FROM cache WHERE key=?", (key,)).fetchone()
                            item = json.loads(cached[0]) if cached else None
                            if item is None:
                                continue
                            found = True
                            if not isinstance(item, dict):
                                raise ValueError("invalid cached details")
                            ext = item.get("external_ids", {})
                            if not isinstance(ext, dict):
                                raise ValueError("invalid cached external IDs")
                            qid = clean(ext.get("wikidata_id"))
                            imdb = clean(ext.get("imdb_id") or item.get("imdb_id"))
                            issue = "conflict" if item.get("id") != tmdb_id else ""
                            if canonical and qid and canonical != qid:
                                issue = "conflict"  # Do not guess redirect equivalence.
                            if ext.get("imdb_id") and item.get("imdb_id") and ext["imdb_id"] != item["imdb_id"]:
                                issue = "conflict"
                            qid = qid or canonical
                            if (qid and not QID.fullmatch(qid)) or (imdb and not IMDB.fullmatch(imdb)):
                                issue = "conflict"
                            self.db.execute("INSERT INTO links VALUES (?,?,?,?,?,?)", (pk, media, tmdb_id, qid, imdb, issue))
                        if not found:
                            self.db.execute("INSERT INTO links VALUES (?,?,?,?,?,?)", (pk, media, tmdb_id, "", "", "unverified_mapping"))
        except (sqlite3.Error, ValueError, TypeError) as error:
            raise CommandError(f"Cannot read a supported import state: {path} ({type(error).__name__}). No Movie writes.") from error

    @staticmethod
    def matches(movie, qid, imdb):
        if (movie.wikidata_id and qid and movie.wikidata_id != qid) or (movie.imdb_id and imdb and movie.imdb_id != imdb):
            raise SourceProblem("conflict")
        return bool((qid and movie.wikidata_id == qid) or (imdb and movie.imdb_id == imdb))

    def local_pair(self, movie):
        rows = self.db.execute("SELECT media,id,qid,imdb,issue FROM links WHERE movie_pk=?", (movie.pk,)).fetchall()
        pairs = set()
        for media, tmdb_id, qid, imdb, issue in rows:
            if issue == "conflict":
                raise SourceProblem("conflict")
            if issue or not self.matches(movie, qid, imdb):
                continue
            pairs.add((media, tmdb_id))
        if len(pairs) > 1:
            raise SourceProblem("conflict")
        if not pairs:
            return None, "unverified_mapping" if rows else "missing_mapping"
        pair = next(iter(pairs))
        if self.db.execute("SELECT 1 FROM links WHERE media=? AND id=? AND movie_pk!=? LIMIT 1", (*pair, movie.pk)).fetchone():
            raise SourceProblem("conflict")
        return pair, ""

    def popularity(self, pair):
        row = self.db.execute("SELECT popularity FROM exports WHERE media=? AND id=?", pair).fetchone()
        return (row[0], "zero_export" if row[0] == 0 else "matched") if row else (0.0, "zero_missing_export")

    def resolve(self, movie, api):
        candidates = set()
        identifiers = [(clean(movie.imdb_id), "imdb_id", IMDB), (clean(movie.wikidata_id), "wikidata_id", QID)]
        valid = [(value, source) for value, source, pattern in identifiers if pattern.fullmatch(value)]
        if not valid:
            raise SourceProblem("missing_identifiers")
        for value, source in valid:
            payload = api.get(f"{TMDB}/find/{value}", {"external_source": source, "language": "en-US"})
            if payload is None:
                continue  # Client only caches None for a confirmed HTTP 404.
            if not isinstance(payload, dict) or not all(isinstance(payload.get(key), list) for key in ("movie_results", "tv_results")):
                raise SourceProblem("source_error")
            for media in ("movie", "tv"):
                for row in payload[f"{media}_results"]:
                    if not isinstance(row, dict) or not positive_id(row.get("id")):
                        raise SourceProblem("source_error")
                    candidates.add((media, row["id"]))
        if len(candidates) > 1:
            raise SourceProblem("conflict")
        if not candidates:
            return 0.0, "zero_find_not_found"
        pair = next(iter(candidates))
        ext = api.get(f"{TMDB}/{pair[0]}/{pair[1]}/external_ids")
        if ext is None:
            return 0.0, "zero_find_not_found"
        if not isinstance(ext, dict) or ext.get("id") != pair[1]:
            raise SourceProblem("source_error")
        # Find supplies exact evidence; external IDs must not contradict it.
        self.matches(movie, clean(ext.get("wikidata_id")), clean(ext.get("imdb_id")))
        return self.popularity(pair)


class Command(BaseCommand):
    help = "Backfill Movie/search popularity from validated daily TMDB exports; never rebuilds search."

    def add_arguments(self, parser):
        parser.add_argument("--movie-export", required=True)
        parser.add_argument("--tv-export", required=True)
        parser.add_argument("--import-state", action="append", default=[], help="Read-only state.sqlite3; repeat for each importer.")
        parser.add_argument("--resolve-missing", action="store_true", help="Opt in to exact TMDB Find requests for unverified/missing mappings.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=0, help="Maximum scanned Movies; 0 means all.")
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument("--after-pk", type=int, default=0)

    def handle(self, *args, **options):
        if options["batch_size"] < 1 or options["limit"] < 0 or options["after_pk"] < 0:
            raise CommandError("batch-size must be positive; limit and after-pk must be nonnegative.")
        if options["resolve_missing"] and not (os.getenv("TMDB_READ_TOKEN") or os.getenv("TMDB_API_KEY")):
            raise CommandError("--resolve-missing requires TMDB_READ_TOKEN or TMDB_API_KEY.")
        counts = Counter()
        last_pk = options["after_pk"]
        with ExitStack() as stack:
            directory = stack.enter_context(tempfile.TemporaryDirectory(prefix="rafs-popularity-"))
            db = stack.enter_context(closing(sqlite3.connect(Path(directory) / "snapshot.sqlite3")))
            snapshot = Snapshot(db)
            date = snapshot.exports({"movie": options["movie_export"], "tv": options["tv_export"]})
            self.stdout.write(f"Validated both exports: snapshot={date}")
            for path in options["import_state"]:
                snapshot.import_state(path)
            api = API(snapshot, os.getenv("TMDB_READ_TOKEN", ""), os.getenv("TMDB_API_KEY", ""),
                      ["en"], self.stdout.write, {"tmdb": 0.6, "wikidata": 1.0, "sparql": 5.0}) if options["resolve_missing"] else None
            if api:
                stack.callback(api.session.close)
            # ContentTypes are created by migrations; dry-run must not create one.
            try:
                content_type = ContentType.objects.get(app_label="movies", model="movie")
            except ContentType.DoesNotExist as error:
                raise CommandError("Movie ContentType missing; apply migrations first.") from error
            if not options["dry_run"]:
                stack.enter_context(database_lock())
            try:
                while not options["limit"] or counts["viewed"] < options["limit"]:
                    size = min(options["batch_size"], options["limit"] - counts["viewed"]) if options["limit"] else options["batch_size"]
                    movies = list(Movie.objects.filter(pk__gt=last_pk).order_by("pk").only("pk", "wikidata_id", "imdb_id", "tmdb_popularity")[:size])
                    if not movies:
                        break
                    resolved, batch_counts = {}, Counter(viewed=len(movies))
                    for movie in movies:
                        try:
                            pair, reason = snapshot.local_pair(movie)
                            if pair:
                                value, reason = snapshot.popularity(pair)
                            elif api:
                                value, reason = snapshot.resolve(movie, api)
                            else:
                                raise SourceProblem(reason)
                            resolved[movie.pk] = (value, movie.wikidata_id, movie.imdb_id)
                            batch_counts[reason] += 1
                            if value == 0:
                                batch_counts["confirmed_zeros"] += 1
                        except SourceProblem as error:
                            batch_counts[str(error)] += 1
                            if str(error) == "source_error":
                                batch_counts["source_invalid_response"] += 1
                            batch_counts["unprocessed"] += 1
                            self.stdout.write(f"Retained pk={movie.pk}: {error}")
                        except CommandError as error:
                            # The shared client exhausts retries before arriving here.
                            message = str(error)
                            category = (
                                "source_http_429" if "HTTP 429" in message else
                                "source_http_5xx" if re.search(r"HTTP 5\d\d", message) else
                                "source_network_error" if "network failure" in message else
                                "source_access_error" if re.search(r"HTTP (401|403)", message) else
                                "source_api_error"
                            )
                            batch_counts["source_error"] += 1
                            batch_counts[category] += 1
                            batch_counts["unprocessed"] += 1
                            self.stdout.write(f"Retained pk={movie.pk}: {category}")
                    self.write_batch(resolved, content_type, options["dry_run"], batch_counts, [movie.pk for movie in movies])
                    counts.update(batch_counts)
                    last_pk = movies[-1].pk
                    self.stdout.write(f"{'DRY RUN' if options['dry_run'] else 'Committed'} batch: last_pk={last_pk}; {json.dumps(dict(sorted(counts.items())))}")
            except KeyboardInterrupt:
                raise CommandError(f"Interrupted; last committed/scanned pk={last_pk}. Repeat unresolved rows separately.") from None
            except DatabaseError as error:
                raise CommandError(f"Batch rolled back ({type(error).__name__}); last committed pk={last_pk}.") from error
            finally:
                keys = ("viewed", "updated_movies", "updated_documents", "confirmed_zeros", "zero_export", "zero_missing_export",
                        "zero_find_not_found", "conflict", "source_error", "missing_mapping", "unverified_mapping",
                        "source_http_429", "source_http_5xx", "source_network_error", "source_access_error",
                        "source_invalid_response", "source_api_error", "missing_identifiers",
                        "concurrent_identity_change", "unprocessed", "missing_documents")
                self.stdout.write(f"{'DRY RUN' if options['dry_run'] else 'RESULT'} last_pk={last_pk}: " + json.dumps({key: counts[key] for key in keys}))

    @staticmethod
    def write_batch(resolved, content_type, dry_run, counts, scanned_ids):
        # Only this short block writes Django. Network and SQLite lookup are done.
        with nullcontext() if dry_run else transaction.atomic():
            movies = Movie.objects.filter(pk__in=resolved).only("pk", "wikidata_id", "imdb_id", "tmdb_popularity")
            if not dry_run:
                movies = movies.select_for_update()
            current = {movie.pk: movie for movie in movies}
            accepted = {}
            changed = []
            for pk, (value, qid, imdb) in resolved.items():
                movie = current.get(pk)
                if movie is None or (movie.wikidata_id, movie.imdb_id) != (qid, imdb):
                    counts["concurrent_identity_change"] += 1
                    counts["unprocessed"] += 1
                    continue
                accepted[pk] = value
                if movie.tmdb_popularity != value:
                    movie.tmdb_popularity = value
                    changed.append(movie)
            documents = GlobalSearchIndex.objects.filter(content_type=content_type, object_id__in=scanned_ids).only("pk", "object_id", "tmdb_popularity")
            if not dry_run:
                documents = documents.select_for_update()
            changed_documents, found = [], set()
            for document in documents:
                found.add(document.object_id)
                if document.object_id in accepted and document.tmdb_popularity != accepted[document.object_id]:
                    document.tmdb_popularity = accepted[document.object_id]
                    changed_documents.append(document)
            counts["missing_documents"] += len(set(scanned_ids) - found)
            counts["updated_movies"] += len(changed)
            counts["updated_documents"] += len(changed_documents)
            if not dry_run:
                Movie.objects.bulk_update(changed, ["tmdb_popularity"])
                GlobalSearchIndex.objects.bulk_update(changed_documents, ["tmdb_popularity"])
