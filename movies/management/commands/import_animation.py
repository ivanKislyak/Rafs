"""Resumable animation campaigns. Written with AI assistance (OpenAI Codex).

Reuses the existing HTTP/identity/fill-only importer. No production import is
triggered by importing this module; see README_import_animation.md.
"""

import hashlib
import json
import math
import os
import signal
import sqlite3
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction

from movies.models import AnimationImportReceipt
from movies.services.animation_state import AnimationState, IMPORTER, MAX_PAGES, SCHEMA_VERSION, saved_config
from movies.services.search_index import refresh_movie_documents

from .import_anime import ANIMATION_GENRE, ANIME_KEYWORD, AnimeAPI, confirmed_format, validate_identity
from .import_popular_movies import (
    MEDIA_FIELDS, REGIONS, RELATIONS, TMDB, Command as MovieCommand,
    ImportIssue, claim_qids, clean, database_lock, import_one, localized_movie, run_lock,
)

BATCH_SIZE = 20
# Verified Wikidata classes: film series, media franchise, fictional character.
# Individual films/shorts and whole TV/web series still require a format root.
COLLECTIVE_TYPES = {"Q24856", "Q196600", "Q95074"}


class CandidateIssue(ImportIssue):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def validate_animation(item, media, tmdb_id, min_votes=0, exclude_anime=False):
    if not item:
        raise CandidateIssue("missing_details", "TMDB details is missing.")
    if type(item.get("id")) is not int or item["id"] != tmdb_id:
        raise CommandError("Unexpected TMDB details ID; campaign stopped.")
    if item.get("adult") or item.get("video"):
        raise CandidateIssue("adult_video", "TMDB marks this record adult/video.")
    if ANIMATION_GENRE not in {row.get("id") for row in item.get("genres", [])}:
        raise CandidateIssue("non_animation", "Animation genre is absent from TMDB details.")
    if (item.get("vote_count") or 0) < min_votes:
        raise CandidateIssue("min_votes", "Below --min-votes.")
    if exclude_anime:
        wrapper = "keywords" if media == "movie" else "results"
        payload = item.get("keywords")
        if not isinstance(payload, dict) or not isinstance(payload.get(wrapper), list):
            raise CommandError("TMDB keyword data is unavailable; exclusion cannot be checked safely. Resume later.")
        if ANIME_KEYWORD in {row.get("id") for row in payload[wrapper]}:
            raise CandidateIssue("excluded_anime", "Exact anime keyword is present in TMDB details.")


@contextmanager
def stopping_signals():
    """Interrupt the current atomic object; subsequent signals cannot break cleanup."""
    stopped = {"signal": None}

    def interrupt(number, frame):
        if stopped["signal"] is None:
            stopped["signal"] = number
            raise KeyboardInterrupt

    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
    try:
        for number in previous:
            signal.signal(number, interrupt)
        yield stopped
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


class Command(MovieCommand):
    help = (
        "Import Animation movie/whole tv works with exact Wikidata identity. "
        "--target-new counts committed new Movie cards across resumes (maximum 15000); "
        "--max-candidates bounds this invocation, including skips. "
        "Written with AI assistance (OpenAI Codex). See README_import_animation.md."
    )

    def add_arguments(self, parser):
        parser.add_argument("--media-type", choices=["movie", "tv", "both"], default="both")
        parser.add_argument("--target-new", type=int, default=15000)
        parser.add_argument("--max-candidates", type=int, default=0, help="Per invocation; 0 = unlimited. Not a new-card target.")
        parser.add_argument("--min-votes", type=int, default=0)
        parser.add_argument("--exclude-anime", action="store_true", help="Exclude the exact anime keyword, not Japanese language/country.")
        parser.add_argument("--languages", default="en,ru,uk,kk,es,de")
        parser.add_argument("--sort", choices=["popularity.desc", "vote_count.desc"], default="popularity.desc")
        parser.add_argument("--date-from", help="Inclusive dated-discovery bound, frozen in campaign. Default 0001-01-01.")
        parser.add_argument("--date-to", help="Inclusive dated-discovery bound, frozen in campaign. Default 9999-12-31.")
        parser.add_argument("--state-dir", default=str(Path(settings.BASE_DIR) / ".rafs_import" / "animation"))
        parser.add_argument("--dry-run", action="store_true", help="Only local discovery/cache/report writes; no Django writes or indexing.")
        parser.add_argument("--retry-skipped", action="store_true")
        parser.add_argument("--refresh-cache", action="store_true", help="Refresh this campaign's API cache; preserve IDs/cursors/receipts.")
        parser.add_argument("--tmdb-delay", type=float, default=0.6)
        parser.add_argument("--wikidata-delay", type=float, default=1.0)
        parser.add_argument("--sparql-delay", type=float, default=5.0)
        parser.add_argument("--maxlag-wait", type=int, default=1800)

    def configuration(self, options, previous):
        if not 1 <= options["target_new"] <= 15000:
            raise CommandError("--target-new must be between 1 and 15000.")
        if any(options[key] < 0 for key in ("min_votes", "max_candidates", "maxlag_wait")):
            raise CommandError("Votes, candidate budget and maxlag wait cannot be negative.")
        if any(not math.isfinite(options[key]) or options[key] < minimum for key, minimum in
               (("tmdb_delay", 0.6), ("wikidata_delay", 1.0), ("sparql_delay", 5.0))):
            raise CommandError("Minimum delays: TMDB 0.6s, Wikidata 1s, SPARQL 5s.")
        languages = list(dict.fromkeys(code.strip() for code in options["languages"].split(",") if code.strip()))
        if "en" not in languages or set(languages) - REGIONS.keys():
            raise CommandError("Supported languages: en,ru,uk,kk,es,de; en is required.")
        try:
            lower = date.fromisoformat(options["date_from"] or (previous or {}).get("date_from", date.min.isoformat()))
            upper = date.fromisoformat(options["date_to"] or (previous or {}).get("date_to", date.max.isoformat()))
            if lower > upper:
                raise ValueError
        except ValueError:
            raise CommandError("Date bounds must be ordered ISO dates YYYY-MM-DD.") from None
        database = settings.DATABASES["default"]
        fingerprint = hashlib.sha256(json.dumps([
            database["ENGINE"], str(database["NAME"]), database.get("HOST", ""),
            str(database.get("PORT", "")), database.get("USER", ""),
        ]).encode()).hexdigest()
        config = {
            "importer": IMPORTER, "schema_version": SCHEMA_VERSION, "database_fingerprint": fingerprint,
            "sources": ["movie", "tv"] if options["media_type"] == "both" else [options["media_type"]],
            "genre": ANIMATION_GENRE, "exclude_anime": options["exclude_anime"],
            "min_votes": options["min_votes"], "languages": languages, "sort": options["sort"],
            "date_from": lower.isoformat(), "date_to": upper.isoformat(),
        }
        if previous is not None and previous != config:
            raise CommandError("State-dir belongs to another database, importer version or selection; use a separate directory.")
        return config

    def handle(self, *args, **options):
        directory = Path(options["state_dir"]).expanduser().resolve()
        config = self.configuration(options, saved_config(directory))
        if connection.vendor != "postgresql":
            raise CommandError("import_animation requires PostgreSQL for shared writer locking and search indexing.")
        try:
            tables = connection.introspection.table_names()
        except Exception as error:
            raise CommandError(f"Database preflight failed ({type(error).__name__}); check the database configuration.") from None
        if AnimationImportReceipt._meta.db_table not in tables:
            raise CommandError("Apply Django migrations (python manage.py migrate) before import_animation.")
        token = clean(os.getenv("TMDB_READ_TOKEN") or getattr(settings, "TMDB_READ_TOKEN", ""))
        key = clean(os.getenv("TMDB_API_KEY") or getattr(settings, "TMDB_API_KEY", ""))
        if not token and not key:
            raise CommandError("Set TMDB_READ_TOKEN or TMDB_API_KEY in .env.")
        self.secrets = [value for value in (token, key) if value]
        self.options, self.config = options, config
        self.run_counts = Counter()
        self.dry_id = str(uuid.uuid4()) if options["dry_run"] else None
        self.stdout.write("Written with AI assistance (OpenAI Codex). Resumable animation campaign.")
        # Both locks fail immediately, rather than queuing behind another writer.
        with run_lock(directory), database_lock(), stopping_signals() as stopped:
            state = AnimationState(directory, config)
            self.state = state
            api = AnimeAPI(state, token, key, config["languages"], self.output, {
                "tmdb": options["tmdb_delay"], "wikidata": options["wikidata_delay"], "sparql": options["sparql_delay"],
            }, maxlag_wait=options["maxlag_wait"])
            self.api = api
            failure, returncode, final = None, 1, "failed"
            try:
                self.receipts = AnimationImportReceipt.objects.filter(campaign=state.campaign)
                self.created_count = self.receipts.filter(outcome="created").count()
                self.last_checkpoint = time.monotonic()
                if not self.dry_id:
                    state.reconcile(self.receipts.order_by("pk"))
                    self.index_pending()
                with state.db:
                    if options["refresh_cache"]:
                        state.db.execute("DELETE FROM cache")
                    if options["retry_skipped"] and not self.dry_id and self.created_count < options["target_new"]:
                        state.db.execute("UPDATE manifest SET status='pending' WHERE status='skipped'")
                if self.created_count < options["target_new"]:
                    if options["exclude_anime"]:
                        keyword = api.get(f"{TMDB}/keyword/{ANIME_KEYWORD}")
                        if not keyword or keyword.get("id") != ANIME_KEYWORD or keyword.get("name") != "anime":
                            raise CommandError("TMDB does not confirm keyword 210024 = anime.")
                    images = (api.get(TMDB + "/configuration") or {}).get("images", {})
                    base, sizes = images.get("secure_base_url", ""), images.get("poster_sizes", [])
                    if not base.startswith("https://image.tmdb.org/") or not sizes:
                        raise CommandError("TMDB image configuration unavailable.")
                    self.image_base = base.rstrip("/") + "/" + ("w500" if "w500" in sizes else sizes[-1])
                final = self.run_campaign()
            except KeyboardInterrupt:
                final = "interrupted"
                returncode = 143 if stopped["signal"] == signal.SIGTERM else 130
                failure = "Interrupted; run the same command to resume."
                state.set_meta("interrupted_runs", state.meta("interrupted_runs", 0) + 1)
            except Exception as error:
                self.run_counts["errors"] += 1
                failure = self.redact(str(error)) if isinstance(error, CommandError) else type(error).__name__
                state.set_meta("failed_runs", state.meta("failed_runs", 0) + 1)
            finally:
                try:
                    try:
                        created = self.receipts.filter(outcome="created").count()
                        summary = self.snapshot(final, created)
                    except DatabaseError:
                        final = "failed"
                        failure = failure or "Database unavailable; authoritative counts will be recovered on resume."
                        summary = {"status": "failed", "campaign": state.campaign,
                                   "created_in_campaign": None, "target_new": options["target_new"],
                                   "count_recovery_on_resume": True, "campaign_state": state.statistics(self.dry_id)}
                    state.report(summary)
                    self.output(json.dumps(summary, ensure_ascii=False))
                except (OSError, sqlite3.Error) as error:
                    raise CommandError(
                        f"failed: local progress/report write failed ({type(error).__name__}). "
                        "Committed Django receipts remain recoverable on resume."
                    ) from None
                finally:
                    api.session.close()
                    state.db.close()
            if failure:
                raise CommandError(f"{final}: {failure}", returncode=returncode) from None

    def redact(self, message):
        for secret in self.secrets:
            message = message.replace(secret, "[redacted]")
        return message

    def output(self, message):
        self.stdout.write(self.redact(message))

    def snapshot(self, status, created):
        run = dict(self.run_counts)
        run["processed"] = sum(value for key, value in run.items() if key not in {"examined", "errors"})
        return {
            "status": status, "campaign": self.state.campaign, "dry_run": bool(self.dry_id),
            "created_in_campaign": created, "target_new": self.options["target_new"],
            "shortfall": max(0, self.options["target_new"] - created),
            "run": run, "campaign_state": self.state.statistics(self.dry_id),
            "pending_index_receipts": self.receipts.filter(indexed=False).count(),
        }

    def checkpoint(self):
        if time.monotonic() - self.last_checkpoint >= 60:
            self.state.write_summary(self.snapshot("running", self.created_count))
            self.last_checkpoint = time.monotonic()

    def run_campaign(self):
        while self.created_count < self.options["target_new"]:
            budget = self.options["max_candidates"]
            remaining = budget - self.run_counts["examined"] if budget else BATCH_SIZE
            if remaining <= 0:
                return "candidate_budget_reached"
            rows = self.state.candidates(min(BATCH_SIZE, remaining), self.dry_id, self.options["retry_skipped"])
            if not rows:
                if not self.discover_round():
                    return "source_exhausted"
                continue
            self.import_batch(rows)
            if not self.dry_id:
                self.index_pending()
            self.checkpoint()
        return "target_reached"

    def discover_round(self):
        pages = []
        for media in self.config["sources"]:
            part = self.state.next_partition(media)
            if part is None:
                continue
            page = part["page"] + 1
            if page > MAX_PAGES:
                raise CommandError("Invalid discovery cursor; page 501 is never requested.")
            parameters = {
                "language": "en-US", "sort_by": self.config["sort"], "page": page,
                "include_adult": "false", "with_genres": str(ANIMATION_GENRE),
                "vote_count.gte": self.config["min_votes"],
            }
            if self.config["exclude_anime"]:
                parameters["without_keywords"] = str(ANIME_KEYWORD)
            if media == "movie":
                parameters["include_video"] = "false"
            else:
                parameters["include_null_first_air_dates"] = "true" if part["mode"] == "unfiltered" else "false"
            if part["mode"] == "dated":
                field = "primary_release_date" if media == "movie" else "first_air_date"
                parameters[field + ".gte"] = part["lower_date"]
                parameters[field + ".lte"] = part["upper_date"]
            self.output(f"Discovery {media}/{part['mode']} {part['lower_date']}..{part['upper_date']} page={page}")
            data = self.api.get(f"{TMDB}/discover/{media}", parameters)
            if (not isinstance(data, dict) or not isinstance(data.get("results"), list)
                    or type(data.get("total_pages")) is not int or data["total_pages"] < 0
                    or any(not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] <= 0 for row in data["results"])):
                raise CommandError("Invalid TMDB discovery response; cursor preserved.")
            if not data["results"] and data["total_pages"] > page:
                raise CommandError("Unexpected empty TMDB discovery page; cursor preserved.")
            if data["results"] and not data["total_pages"]:
                raise CommandError("Inconsistent TMDB discovery totals; cursor preserved.")
            pages.append((part, data))
        if pages:
            self.state.save_pages(pages)
            if hasattr(self, "last_checkpoint"):
                self.checkpoint()
        return bool(pages)

    def finish(self, row, status, *, obj=None, qid="", code="", reason="", count=True):
        self.state.finish(row, status, movie_pk=obj.pk if obj else None, qid=qid, code=code,
                          reason=self.redact(reason), dry_run_id=self.dry_id)
        if count:
            self.run_counts[status] += 1
        self.output(f"{'DRY RUN ' if self.dry_id else ''}{status}: {row['media_type']}/{row['tmdb_id']} {qid} {code}; "
                    f"partition={row['partition_id']} page={row['source_page']}; "
                    f"new={self.created_count}/{self.options['target_new']}")

    def import_batch(self, rows):
        prepared = []
        for row in rows:
            self.state.attempt(row)
            self.run_counts["examined"] += 1
            try:
                item = self.api.details(row["media_type"], row["tmdb_id"])
                validate_animation(item, row["media_type"], row["tmdb_id"], self.config["min_votes"], self.config["exclude_anime"])
                prepared.append((row, item))
            except CandidateIssue as error:
                self.finish(row, "skipped", code=error.code, reason=str(error))
        mappings, issues = {}, {}
        for media in self.config["sources"]:
            items = [item for row, item in prepared if row["media_type"] == media]
            if items:
                media_issues = {}
                result = self.api.resolve(items, media_type=media, issues=media_issues)
                mappings.update({(media, key): value for key, value in result.items()})
                issues.update({(media, key): value for key, value in media_issues.items()})
        entities = self.api.entities(mappings.values(), claims=True) if mappings else {}
        for row, item in prepared:
            if self.created_count >= self.options["target_new"]:
                break  # Every remaining page ID stays pending, even after a SIGKILL.
            pair = (row["media_type"], row["tmdb_id"])
            qid = mappings.get(pair)
            try:
                if not qid:
                    code = issues.get(pair, "no_wikidata_match")
                    raise CandidateIssue(code, "No unique Wikidata match by exact identifiers.")
                entity = entities.get(qid, {})
                if not entity or "missing" in entity:
                    raise CandidateIssue("no_wikidata_match", "The Wikidata identifier does not resolve to an existing entity.")
                validate_identity(entity, item, row["media_type"])
                try:
                    work_type = confirmed_format(entity, row["media_type"], self.api, forbidden_types=COLLECTIVE_TYPES)
                except ImportIssue as error:
                    raise CandidateIssue("invalid_format", str(error)) from None
                texts = localized_movie(item, entity, self.config["languages"], MEDIA_FIELDS[row["media_type"]][0])
                if not any(value.get("wikidata_name") for value in texts.values()):
                    raise CandidateIssue("missing_title", "No usable title in the configured languages.")
                related_ids = {work_type}
                for _, properties in RELATIONS.values():
                    related_ids.update(claim_qids(entity, properties))
                related = self.api.entities(related_ids)
                if not related.get(work_type) or "missing" in related[work_type]:
                    raise CandidateIssue("invalid_format", "The confirmed type entity is unavailable.")
                self.save_candidate(row, item, qid, entity, related, work_type)
            except ImportIssue as error:
                code = getattr(error, "code", None)
                if code is None:
                    ambiguous = any(word in str(error).casefold() for word in ("неоднознач", "несколько"))
                    code = "ambiguous_identity" if ambiguous else "identity_conflict"
                self.finish(row, "skipped", qid=qid or "", code=code, reason=str(error))

    def save_candidate(self, row, item, qid, entity, related, work_type):
        arguments = (item, qid, entity, related, self.config["languages"], self.poster(item))
        keywords = {"media_type": row["media_type"], "confirmed_type": work_type}
        if self.dry_id:
            obj, created = import_one(*arguments, dry_run=True, **keywords)
            duplicate = self.state.db.execute(
                "SELECT 1 FROM manifest WHERE dry_run_id=? AND dry_wikidata_id=? LIMIT 1",
                (self.dry_id, entity["id"]),
            ).fetchone()
            status = "would_duplicate" if duplicate else "would_create" if created else "would_existing"
            self.finish(row, status, obj=obj, qid=entity["id"])
            return
        # ALL network access happened above. This outer transaction ties the
        # receipt to import_one's existing inner atomic Movie/translation/M2M save.
        with transaction.atomic():
            receipt = self.receipts.filter(media_type=row["media_type"], tmdb_id=row["tmdb_id"]).first()
            if receipt is None:
                obj, created = import_one(*arguments, track_changes=True, **keywords)
                outcome = "created" if created else "updated" if obj._import_changed else "existing"
                receipt = AnimationImportReceipt.objects.create(
                    campaign=self.state.campaign, media_type=row["media_type"], tmdb_id=row["tmdb_id"],
                    wikidata_id=entity["id"], movie=obj, outcome=outcome,
                )
                is_new_receipt = True
            else:
                obj, is_new_receipt = receipt.movie, False
        if is_new_receipt and receipt.outcome == "created":
            self.created_count += 1
        if is_new_receipt:
            self.run_counts[receipt.outcome] += 1
        # This may fail after commit; startup reconciles the durable receipt.
        self.finish(row, receipt.outcome, obj=obj, qid=receipt.wikidata_id, count=False)

    def index_pending(self):
        while True:
            receipts = list(self.receipts.filter(indexed=False).order_by("pk")[:BATCH_SIZE])
            if not receipts:
                return
            with transaction.atomic():
                refresh_movie_documents({row.movie_id for row in receipts if row.movie_id is not None})
                self.receipts.filter(pk__in=[row.pk for row in receipts]).update(indexed=True)
