"""Import one title for the staff page on the bulk importers' core.

Same pipeline as import_popular_movies / import_series: TMDB details with
external_ids and translations, exact Wikidata identity (P4947/P4983, IMDb),
entities with claims and relation labels, then the fill-only import_one with
find_existing deduplication. TV needs a Wikidata-confirmed whole-work type,
exactly like import_series.

The commands are reused, not copied, and nothing in them changes. The only
difference is the HTTP layer: a web request keeps its API cache in memory
(no SQLite state, no files) and fails fast instead of waiting minutes.
"""

import json
import logging
import math
import os
import random
import re
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime

import requests
from django.conf import settings
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from movies.management.commands.import_anime import AnimeAPI, confirmed_format, validate_identity
from movies.management.commands.import_animation import COLLECTIVE_TYPES
from movies.management.commands.import_popular_movies import (
    IMDB, MEDIA_FIELDS, QID, REGIONS, RELATIONS, SPARQL, TMDB, ImportIssue, claim_qids, claim_values, clean,
    import_one,
)
from movies.models import Movie
from movies.services.search_index import index_new_persons, index_new_studios, refresh_movie_documents

logger = logging.getLogger(__name__)

# The bulk importers' default set: en, ru, uk, kk, es, de.
LANGUAGES = list(REGIONS)
MEDIA_TYPES = ("movie", "tv")
TMDB_PROPERTIES = {"movie": "P4947", "tv": "P4983"}
POSTER_BASE = "https://image.tmdb.org/t/p/w500"
THUMBNAIL_BASE = "https://image.tmdb.org/t/p/w154"
POSTER_PATH = re.compile(r"/[A-Za-z0-9_.-]+\.(?:jpg|png|webp)", re.I)
MAX_TMDB_ID = 2**31 - 1


class StaffImportError(Exception):
    """An expected failure whose message is safe to show to staff (never a token or URL)."""

    MESSAGES = {
        "invalid": _("The title identifier is not valid."),
        "not_configured": _("TMDB is not configured on the server: TMDB_READ_TOKEN is missing."),
        "source_unavailable": _("TMDB or Wikidata did not respond in time. Try again in a minute."),
        "source_access": _("TMDB or Wikidata refused access. Check the server API credentials."),
        "not_found": _("The title was not found in TMDB or Wikidata."),
        "adult": _("TMDB marks this title as adult content or a video; it is not imported."),
        "no_wikidata": _("No single Wikidata item matches this title by TMDB or IMDb ID, so it was not imported."),
        "ambiguous": _("The Wikidata item lists several TMDB IDs; import it from the TMDB search instead."),
        "identity_conflict": _("TMDB links this title to a different Wikidata item than the one requested."),
        "not_a_work": _("Wikidata does not confirm that this item is a single film or a whole series."),
        "rejected": _("The title was not imported: the sources disagree or a possible duplicate exists."),
        "concurrent": _("The title was imported by someone else at the same time. Open it from the search."),
    }

    def __init__(self, code, detail=""):
        self.code = code
        # Detail comes from the shared importer (its own wording) and never holds secrets.
        self.detail = clean(detail)
        super().__init__(code)

    @property
    def message(self):
        return self.MESSAGES.get(self.code, self.MESSAGES["source_unavailable"])


@dataclass
class ImportResult:
    movie: object
    created: bool
    warnings: list = field(default_factory=list)


class MemoryState:
    """Per-request stand-in for the importers' SQLite State: cache only, no files."""

    def __init__(self):
        self.values = {}

    def cached(self, key):
        return (key in self.values, self.values.get(key))

    def put(self, key, value):
        self.values[key] = value


def tmdb_credentials():
    """Same sources as the commands: environment first, then settings."""
    token = clean(os.getenv("TMDB_READ_TOKEN") or getattr(settings, "TMDB_READ_TOKEN", ""))
    api_key = clean(os.getenv("TMDB_API_KEY") or getattr(settings, "TMDB_API_KEY", ""))
    return token, api_key


class WebAPI(AnimeAPI):
    """The importers' API with a request-sized HTTP policy.

    The commands may wait up to 30 minutes for Wikidata maxlag; a staff page must
    answer in seconds. Everything else (details, entities, resolve, User-Agent,
    Bearer token) is inherited unchanged.
    """

    TIMEOUT = (5, 15)
    ATTEMPTS = 3
    MAX_RETRY_WAIT = 5.0
    DELAYS = {"tmdb": 0.05, "wikidata": 0.2, "sparql": 1.0}

    def __init__(self, token="", api_key=""):
        super().__init__(MemoryState(), token, api_key, LANGUAGES, logger.debug, dict(self.DELAYS), maxlag_wait=0)

    @classmethod
    def from_settings(cls):
        return cls(*tmdb_credentials())

    @property
    def has_tmdb(self):
        return bool(self.token or self.api_key)

    def get(self, url, params=None):
        params = dict(params or {})
        key = json.dumps([url, params], sort_keys=True)
        found, cached = self.state.cached(key)
        if found:
            return cached
        family = "tmdb" if url.startswith(TMDB + "/") else "sparql" if url == SPARQL else "wikidata"
        headers = {}
        if family == "tmdb":
            if self.token:
                headers["Authorization"] = "Bearer " + self.token
            elif self.api_key:
                params["api_key"] = self.api_key
            else:
                raise StaffImportError("not_configured")
        elif family == "sparql":
            headers["Accept"] = "application/sparql-results+json"
        reason = "no response"
        for attempt in range(self.ATTEMPTS):
            wait = self.next_request[family] - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.next_request[family] = time.monotonic() + self.delays[family]
            response = None
            try:
                response = self.session.get(url, params=params, headers=headers, timeout=self.TIMEOUT)
            except requests.RequestException as error:
                # Only the class name: a requests error message may contain the URL.
                reason = type(error).__name__
            else:
                status = response.status_code
                if status == 404:
                    self.state.put(key, None)
                    return None
                if status in (401, 403):
                    logger.warning("%s refused access: HTTP %s", family, status)
                    raise StaffImportError("source_access")
                if status == 429 or status >= 500:
                    reason = f"HTTP {status}"
                elif status >= 400:
                    logger.warning("%s rejected the request: HTTP %s", family, status)
                    raise StaffImportError("source_unavailable")
                else:
                    try:
                        payload = response.json()
                    except ValueError:
                        reason = "invalid JSON"
                    else:
                        if isinstance(payload, dict) and not payload.get("error"):
                            self.state.put(key, payload)
                            return payload
                        # Wikidata maxlag/ratelimited arrive as an error body with HTTP 200.
                        error = payload.get("error") if isinstance(payload, dict) else None
                        reason = clean(error.get("code")) if isinstance(error, dict) else "unexpected JSON"
            if attempt + 1 == self.ATTEMPTS:
                break
            delay = self.retry_delay(response, attempt)
            if delay is None:
                break
            time.sleep(delay)
        logger.warning("%s request failed after retries: %s", family, reason)
        raise StaffImportError("source_unavailable")

    def retry_delay(self, response, attempt):
        """Short backoff; give up at once if the server asks to wait longer than a page can."""
        delay = 0.5 * 2**attempt + random.uniform(0, 0.25)
        retry = response.headers.get("Retry-After", "") if response is not None else ""
        if retry:
            try:
                seconds = float(retry)
            except ValueError:
                try:
                    seconds = parsedate_to_datetime(retry).timestamp() - time.time()
                except (TypeError, ValueError, OverflowError):
                    seconds = 0
            delay = max(delay, seconds)
        return delay if delay <= self.MAX_RETRY_WAIT else None


def poster_url(item, base=POSTER_BASE):
    """Same rule as the commands' poster(): a w500 TMDB URL for a plain image path."""
    path = clean(item.get("poster_path"))
    return base + path if POSTER_PATH.fullmatch(path) else ""


def tmdb_popularity(item):
    """Validated like backfill_tmdb_popularity: finite and non-negative, else unknown."""
    value = item.get("popularity")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0 else None


def valid_tmdb_id(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= MAX_TMDB_ID


def related_entities(api, entity, extra=()):
    """Labels of the work's type and of every relation, as import_manifest fetches them."""
    qids = set(extra) | set(claim_qids(entity, ("P31",)))
    for _model, properties in RELATIONS.values():
        qids.update(claim_qids(entity, properties))
    return api.entities(qids)


def save_title(item, qid, entity, related, media_type, confirmed_type, popularity):
    """import_one (fill-only, find_existing) plus popularity, in one transaction."""
    try:
        with transaction.atomic():
            movie, created = import_one(
                item, qid, entity, related, LANGUAGES, poster_url(item),
                media_type=media_type, confirmed_type=confirmed_type, track_changes=True,
            )
            if popularity is not None and movie.tmdb_popularity != popularity:
                movie.tmdb_popularity = popularity
                movie.save(update_fields=["tmdb_popularity"])
            result = ImportResult(movie, created)
            if search_index_supported():
                # Relation names are already written above; the index reads them after commit.
                transaction.on_commit(lambda: index_title(result))
    except ImportIssue as issue:
        raise StaffImportError("rejected", str(issue)) from None
    except IntegrityError:
        # Unique wikidata_id: another import committed the same work in between.
        raise StaffImportError("concurrent") from None
    return result


INDEX_WARNING = _(
    "The title was saved but is not searchable yet: search indexing failed. "
    "Add it again later or run rebuild_search_index."
)


def search_index_supported():
    """Full-text documents exist only on PostgreSQL, as for rebuild_search_index."""
    return connection.vendor == "postgresql"


def index_title(result):
    """After commit: the title's own document, then people and studios not yet indexed.

    A failure never undoes the import: it is logged and shown to staff as a warning.
    """
    try:
        refresh_movie_documents([result.movie.pk])
        index_new_persons()
        index_new_studios()
    except Exception:
        logger.exception("Search indexing failed after the staff import of movie %s", result.movie.pk)
        result.warnings.append(INDEX_WARNING)


def import_tmdb(media_type, tmdb_id, *, api=None, expected_qid=None):
    """Full import by TMDB ID, the same steps as one row of the bulk import."""
    if media_type not in MEDIA_TYPES or not valid_tmdb_id(tmdb_id):
        raise StaffImportError("invalid")
    api = api or WebAPI.from_settings()
    if not api.has_tmdb:
        raise StaffImportError("not_configured")
    try:
        item = api.details(media_type, tmdb_id)
        if not item:
            raise StaffImportError("not_found")
        if item.get("id") != tmdb_id:
            logger.warning("TMDB details returned an unexpected ID for %s/%s", media_type, tmdb_id)
            raise StaffImportError("source_unavailable")
        if item.get("adult") or item.get("video"):
            raise StaffImportError("adult")
        issues = {}
        qid = api.resolve([item], media_type=media_type, issues=issues).get(tmdb_id)
        if not qid:
            raise StaffImportError("no_wikidata", issues.get(tmdb_id, ""))
        entity = api.entities([qid], claims=True).get(qid) or {}
        if not entity or "missing" in entity:
            raise StaffImportError("no_wikidata")
        if expected_qid and expected_qid not in {qid, entity.get("id")}:
            raise StaffImportError("identity_conflict")
        confirmed_type = None
        if media_type == "tv":
            # As import_series: whole series only, type confirmed through P31/P279.
            validate_identity(entity, item, media_type)
            confirmed_type = confirmed_format(entity, media_type, api, forbidden_types=COLLECTIVE_TYPES)
        related = related_entities(api, entity, {"Q11424", *([confirmed_type] if confirmed_type else [])})
    except ImportIssue as issue:
        raise StaffImportError("rejected", str(issue)) from None
    except CommandError:
        # The inherited helpers stop with CommandError on an incomplete source response.
        raise StaffImportError("source_unavailable") from None
    return save_title(item, qid, entity, related, media_type, confirmed_type, tmdb_popularity(item))


def work_format(entity, api):
    """Wikidata-only path: the item must be a confirmed film or a confirmed whole series."""
    last_issue = None
    for media_type in MEDIA_TYPES:
        try:
            return media_type, confirmed_format(entity, media_type, api, forbidden_types=COLLECTIVE_TYPES)
        except ImportIssue as issue:
            last_issue = issue
    raise StaffImportError("not_a_work", str(last_issue or ""))


def import_qid(qid, *, api=None):
    """Add by QID: the TMDB path when the item names its TMDB ID, else Wikidata alone."""
    qid = clean(qid)
    if not QID.fullmatch(qid):
        raise StaffImportError("invalid")
    api = api or WebAPI.from_settings()
    try:
        entity = api.entities([qid], claims=True).get(qid) or {}
        if not entity or "missing" in entity:
            raise StaffImportError("not_found")
        candidates = {
            (media_type, int(value))
            for media_type, prop in TMDB_PROPERTIES.items()
            for value in map(clean, claim_values(entity, prop))
            if value.isdigit() and valid_tmdb_id(int(value))
        }
        if len(candidates) > 1:
            raise StaffImportError("ambiguous")
        if candidates:
            media_type, tmdb_id = next(iter(candidates))
            return import_tmdb(media_type, tmdb_id, api=api, expected_qid=clean(entity.get("id")) or qid)
        media_type, confirmed_type = work_format(entity, api)
        related = related_entities(api, entity, {confirmed_type})
    except CommandError:
        raise StaffImportError("source_unavailable") from None
    # No TMDB record: titles, descriptions and the year come from Wikidata alone.
    item = {"id": None, "external_ids": {}}
    return save_title(item, qid, entity, related, media_type, confirmed_type, None)


@dataclass
class SearchResult:
    media_type: str
    tmdb_id: int
    title: str
    original_title: str
    year: int | None
    poster: str
    overview: str
    wikidata_id: str = ""
    imdb_id: str = ""
    movie: object = None
    # False when TMDB external IDs could not be read: "already in the catalogue" is then unknown.
    identity_checked: bool = False


def search_tmdb(query, language, *, api=None, limit=10):
    """TMDB search over films and series, marked with the catalogue copy found by QID or IMDb.

    Movie has no TMDB ID column, so each result's external_ids gives the QID/IMDb
    to compare; that is one short request per shown result.
    """
    api = api or WebAPI.from_settings()
    if not api.has_tmdb:
        raise StaffImportError("not_configured")
    region = REGIONS.get(language, "US")
    data = api.get(f"{TMDB}/search/multi", {
        "query": query, "language": f"{language}-{region}", "include_adult": "false", "page": 1,
    })
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise StaffImportError("source_unavailable")
    rows = [
        row for row in data["results"]
        if isinstance(row, dict) and row.get("media_type") in MEDIA_TYPES
        and valid_tmdb_id(row.get("id")) and not row.get("adult")
    ][:limit]
    results, identities_available = [], True
    for row in rows:
        media_type = row["media_type"]
        title_field, date_field, _property = MEDIA_FIELDS[media_type]
        release = clean(row.get(date_field))
        result = SearchResult(
            media_type=media_type, tmdb_id=row["id"],
            title=clean(row.get(title_field)),
            original_title=clean(row.get("original_title" if media_type == "movie" else "original_name")),
            year=int(release[:4]) if re.match(r"^[1-9]\d{3}-", release) else None,
            poster=poster_url(row, THUMBNAIL_BASE), overview=clean(row.get("overview")),
        )
        if identities_available:
            try:
                ids = api.get(f"{TMDB}/{media_type}/{row['id']}/external_ids") or {}
            except StaffImportError:
                # Do not wait on every remaining result when the source is failing.
                identities_available = False
            else:
                qid, imdb = clean(ids.get("wikidata_id")), clean(ids.get("imdb_id"))
                result.wikidata_id = qid if QID.fullmatch(qid) else ""
                result.imdb_id = imdb if IMDB.fullmatch(imdb) else ""
                result.identity_checked = True
        results.append(result)
    attach_catalogue_movies(results)
    return results


def attach_catalogue_movies(results):
    """One query: the catalogue copy of each result, by Wikidata ID first, then IMDb."""
    qids = {r.wikidata_id for r in results if r.wikidata_id}
    imdbs = {r.imdb_id for r in results if r.imdb_id}
    if not qids and not imdbs:
        return
    movies = Movie.objects.filter(Q(wikidata_id__in=qids) | Q(imdb_id__in=imdbs)).only("pk", "name", "wikidata_id", "imdb_id")
    by_qid, by_imdb = {}, {}
    for movie in movies:
        if movie.wikidata_id:
            by_qid[movie.wikidata_id] = movie
        if movie.imdb_id:
            by_imdb.setdefault(movie.imdb_id, movie)
    for result in results:
        result.movie = by_qid.get(result.wikidata_id) or by_imdb.get(result.imdb_id)
