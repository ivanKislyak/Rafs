"""RAFS catalogue importer. Written with AI assistance (OpenAI Codex).

Place in movies/management/commands/import_popular_movies.py.
No model changes. TMDB supplies discovery, translations and poster URLs;
Wikidata supplies stable identity, multilingual labels and catalogue relations.
Only verified Wikidata-backed movies are created. No fuzzy title matching.
"""

import csv
import hashlib
import json
import math
import os
import random
import re
import sqlite3
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from movies.models import Movie
from movies.movie_models import Country, Genre, Person, Studio, TypeOfWork

TMDB = "https://api.themoviedb.org/3"
WIKIDATA = "https://www.wikidata.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"
USER_AGENT = (
    "RafsCatalogImporter/1.0 "
    "(https://github.com/ivanKislyak/Rafs; contact: kislyakhelp@gmail.com)"
)
RELATIONS = {
    "genres": (Genre, ("P136",)),
    "countries": (Country, ("P495",)),
    "studio": (Studio, ("P272",)),
    "actors": (Person, ("P161", "P725")),
    "director": (Person, ("P57",)),
    "producer": (Person, ("P162",)),
    "screenwriter": (Person, ("P58",)),
    "composer": (Person, ("P86",)),
}
REGIONS = {"en": "US", "ru": "RU", "uk": "UA", "kk": "KZ", "es": "ES", "de": "DE"}
QID = re.compile(r"Q[1-9]\d*\Z")
IMDB = re.compile(r"tt\d+\Z")
MEDIA_FIELDS = {
    "movie": ("title", "release_date", "P4947"),
    "tv": ("name", "first_air_date", "P4983"),
}


def clean(value):
    return str(value).strip() if value is not None else ""


def batches(values, size=50):
    values = list(values)
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


def claim_values(entity, prop):
    """Keep all non-deprecated value statements; ignore unknown/no-value snaks."""
    result = []
    for statement in entity.get("claims", {}).get(prop, []):
        if statement.get("rank") == "deprecated":
            continue
        snak = statement.get("mainsnak", {})
        if snak.get("snaktype") == "value" and "datavalue" in snak:
            result.append(snak["datavalue"]["value"])
    return result


def claim_qids(entity, properties):
    return sorted({
        value["id"] for prop in properties for value in claim_values(entity, prop)
        if isinstance(value, dict) and QID.fullmatch(clean(value.get("id")))
    })


class ImportIssue(Exception):
    """One ambiguous/unusable item; may be skipped without stopping the run."""


class State:
    """Durable manifest and API cache, separate from the application's database."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.directory / "state.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS manifest (
                position INTEGER PRIMARY KEY AUTOINCREMENT,
                tmdb_id INTEGER UNIQUE NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                movie_pk INTEGER, reason TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS covers (
                movie_pk INTEGER PRIMARY KEY, status TEXT NOT NULL, reason TEXT NOT NULL
            );
        """)
        self.db.commit()

    def meta(self, key, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_meta(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value)))
        self.db.commit()

    def cached(self, key):
        row = self.db.execute("SELECT value FROM cache WHERE key=?", (key,)).fetchone()
        return (True, json.loads(row[0])) if row else (False, None)

    def put(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO cache VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False)))
        self.db.commit()

    def mark(self, tmdb_id, status, movie_pk=None, reason=""):
        self.db.execute("UPDATE manifest SET status=?, movie_pk=?, reason=? WHERE tmdb_id=?",
                        (status, movie_pk, reason, tmdb_id))
        self.db.commit()

    def cover_mark(self, pk, status, reason=""):
        self.db.execute("INSERT OR REPLACE INTO covers VALUES (?,?,?)", (pk, status, reason))
        self.db.commit()

    def report(self):
        for name, query in (
            ("import_report.csv", "SELECT * FROM manifest ORDER BY position"),
            ("cover_report.csv", "SELECT * FROM covers ORDER BY movie_pk"),
        ):
            cursor = self.db.execute(query)
            with (self.directory / name).open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow([column[0] for column in cursor.description])
                writer.writerows(cursor)


@contextmanager
def run_lock(directory):
    """OS lock is automatically released even if the process is killed."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    with (path / "run.lock").open("a+b") as stream:
        stream.seek(0)
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise CommandError("Импорт с этим state-dir уже запущен.") from error
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise CommandError("Импорт с этим state-dir уже запущен.") from error
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def database_lock():
    """Serialize this importer across different state directories on PostgreSQL."""
    if connection.vendor != "postgresql":
        yield
        return
    lock_id = 704913204817
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [lock_id])
        if not cursor.fetchone()[0]:
            raise CommandError("Другой импорт RAFS уже работает с этой PostgreSQL.")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_id])


class API:
    def __init__(self, state, token, api_key, languages, output, delays, maxlag_wait=1800):
        self.state, self.languages, self.output = state, languages, output
        self.token, self.api_key = token, api_key
        self.delays = delays
        self.maxlag_wait = maxlag_wait
        self.next_request = defaultdict(float)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    def get(self, url, params=None):
        params = dict(params or {})
        key = "http:" + hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()
        found, cached = self.state.cached(key)
        if found:
            return cached
        family = "tmdb" if url.startswith(TMDB + "/") else "sparql" if url == SPARQL else "wikidata"
        headers = {}
        if family == "tmdb":
            if self.token:
                headers["Authorization"] = "Bearer " + self.token
            else:
                params["api_key"] = self.api_key
        elif family == "sparql":
            headers["Accept"] = "application/sparql-results+json"
        attempt = 0
        maxlag_started = None
        while attempt < 6:
            wait = self.next_request[family] - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.next_request[family] = time.monotonic() + self.delays[family] + random.uniform(0, 0.15)
            response = None
            maxlag_error = None
            reason = "temporary network failure"
            try:
                response = self.session.get(url, params=params, headers=headers, timeout=(15, 70))
                if response.status_code in (401, 403):
                    raise CommandError(f"{family}: HTTP {response.status_code}. Остановка; проверь ключ/доступ. Повторные запросы не отправляются.")
                if response.status_code == 404:
                    self.state.put(key, None)
                    return None
                if response.status_code == 429 or response.status_code >= 500:
                    reason = f"HTTP {response.status_code}"
                    if family == "wikidata":
                        try:
                            body = response.json()
                            error = body.get("error", {}) if isinstance(body, dict) else {}
                            if isinstance(error, dict) and error.get("code") == "maxlag":
                                maxlag_error = error
                        except ValueError:
                            pass
                elif response.status_code >= 400:
                    raise CommandError(f"{family}: HTTP {response.status_code}; исправь запрос перед продолжением.")
                else:
                    payload = response.json()
                    if not isinstance(payload, dict):
                        reason = "unexpected JSON"
                    elif payload.get("error"):
                        error = payload["error"]
                        code = error.get("code", "unknown") if isinstance(error, dict) else "unknown"
                        if code not in {"maxlag", "ratelimited", "readonly", "internal_api_error_DBQueryError"}:
                            raise CommandError(f"{family}: API error {code}.")
                        reason = code
                        if code == "maxlag":
                            maxlag_error = error
                    else:
                        self.state.put(key, payload)
                        return payload
            except (requests.Timeout, requests.ConnectionError, ValueError):
                pass
            except requests.RequestException as error:
                raise CommandError(f"{family}: {type(error).__name__}; остановка.") from error
            delay = (60 if maxlag_error is not None else min(120, 5 * 2 ** attempt)) + random.uniform(0, 2)
            retry = response.headers.get("Retry-After", "") if response is not None else ""
            if retry:
                try:
                    retry_seconds = float(retry)
                except ValueError:
                    try:
                        retry_seconds = parsedate_to_datetime(retry).timestamp() - time.time()
                    except (ValueError, TypeError, OverflowError):
                        retry_seconds = 0
                delay = max(delay, retry_seconds)
            if maxlag_error is not None:
                now = time.monotonic()
                if maxlag_started is None:
                    maxlag_started = now
                elapsed = now - maxlag_started
                if elapsed + delay > self.maxlag_wait:
                    raise CommandError(
                        f"Wikidata всё ещё сообщает maxlag; бюджет ожидания {self.maxlag_wait} с исчерпан. "
                        "Повтори команду позже или увеличь --maxlag-wait; maxlag=5 сохранён."
                    )
                self.output(
                    f"wikidata: maxlag (задержка сервиса: {maxlag_error.get('lag', '?')} с); "
                    f"ожидание {delay:.0f} с, прошло {elapsed / 60:.1f} из {self.maxlag_wait / 60:.0f} мин."
                )
                self.next_request[family] = max(self.next_request[family], now + delay)
                continue
            if attempt == 5:
                raise CommandError(f"{family}: {reason}; исчерпаны повторы. Запусти ту же команду позже — прогресс сохранён.")
            if delay > 900:
                raise CommandError(f"{family}: сервер требует ждать более 15 минут. Остановка; повтори позже.")
            self.output(f"{family}: {reason}; ожидание {delay:.0f} с, повтор {attempt + 1}/5.")
            self.next_request[family] = max(self.next_request[family], time.monotonic() + delay)
            attempt += 1

    def details(self, tmdb_id):
        return self.get(f"{TMDB}/movie/{tmdb_id}", {
            "language": "en-US", "append_to_response": "external_ids,translations",
        })

    def entities(self, qids, claims=False):
        result, missing = {}, []
        props = "labels|descriptions|claims" if claims else "labels"
        prefix = "entity:" + props + ":" + ",".join(self.languages) + ":"
        for qid in sorted(set(qids)):
            if not QID.fullmatch(clean(qid)):
                continue
            found, entity = self.state.cached(prefix + qid)
            if found:
                result[qid] = entity
            else:
                missing.append(qid)
        for group in batches(missing):
            payload = self.get(WIKIDATA, {
                "action": "wbgetentities", "ids": "|".join(group), "props": props,
                "languages": "|".join(self.languages), "format": "json", "formatversion": 2,
                "redirects": "yes", "maxlag": 5,
            })
            if not payload or "entities" not in payload:
                raise CommandError("Wikidata не вернул entities; прогресс сохранён.")
            redirects = {x["from"]: x["to"] for x in payload.get("redirects", [])}
            for qid in group:
                entity = payload["entities"].get(redirects.get(qid, qid), {})
                self.state.put(prefix + qid, entity)
                result[qid] = entity
        return result

    def resolve(self, details, media_type="movie"):
        """Batch exact-ID lookup; movie remains the existing command's default."""
        tmdb_property = MEDIA_FIELDS[media_type][2]
        result, unresolved = {}, []
        for item in details:
            ext = item.get("external_ids", {})
            qid = clean(ext.get("wikidata_id"))
            imdb = clean(ext.get("imdb_id") or item.get("imdb_id"))
            if QID.fullmatch(qid):
                result[item["id"]] = qid
            else:
                existing = list(Movie.objects.filter(imdb_id=imdb).exclude(wikidata_id__isnull=True)
                                .exclude(wikidata_id="").values_list("wikidata_id", flat=True)) if IMDB.fullmatch(imdb) else []
                if len(existing) == 1 and QID.fullmatch(existing[0]):
                    result[item["id"]] = existing[0]
                else:
                    unresolved.append(item)
        if not unresolved:
            return result
        tmdb_literals = " ".join(json.dumps(str(x["id"])) for x in unresolved)
        imdb_values = {clean(x.get("external_ids", {}).get("imdb_id") or x.get("imdb_id")) for x in unresolved}
        imdb_literals = " ".join(json.dumps(x) for x in sorted(imdb_values) if IMDB.fullmatch(x))
        branches = [f'{{ VALUES ?identifier {{ {tmdb_literals} }} ?item wdt:{tmdb_property} ?identifier . BIND("tmdb" AS ?source) }}']
        if imdb_literals:
            branches.append(f'{{ VALUES ?identifier {{ {imdb_literals} }} ?item wdt:P345 ?identifier . BIND("imdb" AS ?source) }}')
        query = ('PREFIX wdt: <http://www.wikidata.org/prop/direct/> '
                 'SELECT DISTINCT ?item ?identifier ?source WHERE { ' + ' UNION '.join(branches) + ' }')
        data = self.get(SPARQL, {"query": query, "format": "json"})
        if not data or "results" not in data:
            raise CommandError("SPARQL не вернул results; повтори позже.")
        mappings = defaultdict(set)
        for row in data["results"]["bindings"]:
            qid = row["item"]["value"].rsplit("/", 1)[-1]
            if QID.fullmatch(qid):
                mappings[(row["source"]["value"], row["identifier"]["value"])].add(qid)
        for item in unresolved:
            imdb = clean(item.get("external_ids", {}).get("imdb_id") or item.get("imdb_id"))
            qids = mappings[("tmdb", str(item["id"]))] | mappings[("imdb", imdb)]
            if len(qids) == 1:
                result[item["id"]] = next(iter(qids))
        return result


def limit_text(model, field, value):
    value = clean(value)
    length = model._meta.get_field(field).max_length
    return value[:length] if length else value


def fill_translations(obj, translations):
    """Save each actual language separately; never use parler language fallbacks."""
    model = obj._parler_meta.root_model
    changed = 0
    for language, fields in translations.items():
        row = model.objects.filter(master=obj, language_code=language).first()
        if row is None:
            row = model(master=obj, language_code=language)
        touched = []
        for field, text in fields.items():
            text = limit_text(model, field, text)
            if text and not clean(getattr(row, field, "")):
                setattr(row, field, text)
                touched.append(field)
        if touched:
            row.save()
            changed += 1
    return changed


def localized_movie(item, entity, languages, title_field="title"):
    variants = defaultdict(list)
    for row in item.get("translations", {}).get("translations", []):
        variants[row.get("iso_639_1")].append(row)
    result = {}
    for language in languages:
        options = sorted(variants[language], key=lambda x: x.get("iso_3166_1") != REGIONS.get(language))
        title = next((clean(x.get("data", {}).get(title_field)) for x in options if clean(x.get("data", {}).get(title_field))), "")
        overview = next((clean(x.get("data", {}).get("overview")) for x in options if clean(x.get("data", {}).get("overview"))), "")
        label = clean(entity.get("labels", {}).get(language, {}).get("value"))
        description = clean(entity.get("descriptions", {}).get(language, {}).get("value"))
        if language == "en":
            overview = overview or clean(item.get("overview"))
            title = title or label or clean(item.get(title_field))
        values = {"wikidata_name": title or label, "wikidata_description": overview or description}
        if any(values.values()):
            result[language] = values
    return result


def find_existing(qid, original_qid, imdb, names, year):
    identities = Q(wikidata_id__in={qid, original_qid})
    if imdb:
        identities |= Q(imdb_id=imdb)
    matches = list(Movie.objects.filter(identities).order_by("pk")[:3])
    if len(matches) > 1:
        raise ImportIssue("Несколько существующих записей совпали по QID/IMDb; нужен ручной разбор.")
    if matches:
        obj = matches[0]
        if obj.wikidata_id and obj.wikidata_id not in {qid, original_qid}:
            raise ImportIssue("IMDb совпал, но Wikidata ID отличается.")
        if obj.imdb_id and imdb and obj.imdb_id != imdb:
            raise ImportIssue("Wikidata совпал, но IMDb ID отличается.")
        return obj
    # A legacy title match is not strong enough to merge, but is strong enough
    # to stop automatic insertion and prevent a likely duplicate.
    if year and names:
        title_query = Q(pk__in=[])
        for name in names:
            title_query |= Q(name__iexact=name) | Q(translations__wikidata_name__iexact=name)
        if Movie.objects.filter(title_query).filter(Q(year=year) | Q(year__isnull=True)).exists():
            raise ImportIssue("Есть фильм с тем же названием и годом без совпадения ID; проверь вручную.")
    return None


def relation_data(entity, related_entities, languages):
    result = {}
    for field, (model, props) in RELATIONS.items():
        result[field] = []
        for qid in claim_qids(entity, props):
            data = related_entities.get(qid, {})
            if not data or "missing" in data:
                continue
            obj, _ = model.objects.get_or_create(wikidata_id=qid)
            fill_translations(obj, {
                lang: {"name": data.get("labels", {}).get(lang, {}).get("value", "")}
                for lang in languages
            })
            result[field].append(obj)
    return result


def import_one(item, original_qid, entity, related_entities, languages, poster_url, dry_run=False,
               *, media_type="movie", confirmed_type=None):
    title_field, date_field, tmdb_property = MEDIA_FIELDS[media_type]
    if media_type == "tv" and not confirmed_type:
        raise ImportIssue("Для TV необходим подтверждённый тип произведения; film по умолчанию запрещён.")
    if confirmed_type and confirmed_type not in claim_qids(entity, ("P31",)):
        raise ImportIssue("Тип произведения не подтверждён P31 Wikidata.")
    qid = clean(entity.get("id"))
    if not QID.fullmatch(qid) or "missing" in entity:
        raise ImportIssue("Wikidata entity отсутствует.")
    imdb = clean(item.get("external_ids", {}).get("imdb_id") or item.get("imdb_id"))
    wd_imdbs = {x for x in claim_values(entity, "P345") if isinstance(x, str) and IMDB.fullmatch(x)}
    if imdb and not IMDB.fullmatch(imdb):
        raise ImportIssue("Некорректный IMDb ID от TMDB.")
    if imdb and wd_imdbs and imdb not in wd_imdbs:
        raise ImportIssue("TMDB и Wikidata сообщают разные IMDb ID.")
    if not imdb and len(wd_imdbs) == 1:
        imdb = next(iter(wd_imdbs))
    tmdb_ids = {clean(x) for x in claim_values(entity, tmdb_property)}
    if tmdb_ids and str(item["id"]) not in tmdb_ids:
        raise ImportIssue("TMDB и Wikidata сообщают разные TMDB ID.")
    release = clean(item.get(date_field))
    year = int(release[:4]) if re.match(r"^[1-9]\d{3}-\d{2}-\d{2}$", release) else None
    if year is None:
        years = []
        date_properties = ("P580", "P577") if media_type == "tv" else ("P577",)
        for value in (value for prop in date_properties for value in claim_values(entity, prop)):
            time_value = clean(value.get("time")) if isinstance(value, dict) else ""
            match = re.match(r"^\+(\d{4})-", time_value)
            if match and 0 < int(match[1]) < 10000:
                years.append(int(match[1]))
        year = min(years) if years else None
    texts = localized_movie(item, entity, languages, title_field)
    names = {v["wikidata_name"] for v in texts.values() if v["wikidata_name"]}
    names.update(clean(value.get("value")) for value in entity.get("labels", {}).values())
    names.add(clean(item.get(title_field)))
    obj = find_existing(qid, original_qid, imdb, {x for x in names if x}, year)
    created = obj is None
    if dry_run:
        return obj, created
    with transaction.atomic():
        # Repeat under transaction after fetching remote data outside the lock.
        obj = find_existing(qid, original_qid, imdb, {x for x in names if x}, year)
        created = obj is None
        if obj is None:
            obj = Movie.objects.create(
                wikidata_id=qid, imdb_id=imdb or None, year=year,
                name=limit_text(Movie, "name", texts.get("en", {}).get("wikidata_name") or item.get(title_field) or qid),
                description=clean(texts.get("en", {}).get("wikidata_description")),
                cover_url=poster_url,
            )
        fields = []
        for field, value in (("wikidata_id", qid), ("imdb_id", imdb or None), ("year", year),
                             ("name", texts.get("en", {}).get("wikidata_name")),
                             ("description", texts.get("en", {}).get("wikidata_description"))):
            if not getattr(obj, field) and value:
                setattr(obj, field, limit_text(Movie, field, value) if isinstance(value, str) else value)
                fields.append(field)
        if not obj.cover and not obj.cover_url and poster_url:
            obj.cover_url = poster_url
            fields.append("cover_url")
        if obj.type_of_work_id is None:
            types = claim_qids(entity, ("P31",))
            type_qid = confirmed_type or ("Q11424" if "Q11424" in types else next(iter(types), "Q11424"))
            type_obj, _ = TypeOfWork.objects.get_or_create(wikidata_id=type_qid)
            type_data = related_entities.get(type_qid, {})
            fill_translations(type_obj, {lang: {"name": type_data.get("labels", {}).get(lang, {}).get("value", "")}
                                          for lang in languages})
            obj.type_of_work = type_obj
            fields.append("type_of_work")
        obj.last_synced_at = timezone.now()
        fields.append("last_synced_at")
        obj.save(update_fields=fields)
        fill_translations(obj, texts)
        for field, objects in relation_data(entity, related_entities, languages).items():
            if objects:
                getattr(obj, field).add(*objects)
        return obj, created


class Command(BaseCommand):
    help = "Импорт до 10 000 популярных фильмов TMDB + Wikidata. Написан с помощью ИИ (OpenAI Codex)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10000, help="Размер списка кандидатов, включая пропуски; максимум 10000.")
        parser.add_argument("--languages", default="en,ru,uk,kk,es,de")
        parser.add_argument("--min-votes", type=int, default=50)
        parser.add_argument("--sort", choices=["popularity.desc", "vote_count.desc"], default="popularity.desc")
        parser.add_argument("--without-genres", default="16", help="По умолчанию исключена анимация; пустая строка отключает фильтр.")
        parser.add_argument("--state-dir", default=str(Path(settings.BASE_DIR) / ".rafs_import"))
        parser.add_argument("--dry-run", action="store_true", help="Не менять Django БД; API-кэш и список кандидатов сохраняются.")
        parser.add_argument("--covers-only", action="store_true", help="Только недостающие обложки существующих фильмов.")
        parser.add_argument("--skip-backfill", action="store_true", help="Не искать обложки существующих фильмов.")
        parser.add_argument("--backfill-limit", type=int, default=0, help="0 = все существующие фильмы без обложки.")
        parser.add_argument("--retry-skipped", action="store_true", help="Повторить неоднозначные/пропущенные записи после ручных исправлений.")
        parser.add_argument("--reprocess", action="store_true", help="Повторно заполнить пустые поля ранее импортированных кандидатов; без удаления данных.")
        parser.add_argument("--refresh-cache", action="store_true", help="Обновить ответы API; не удаляет записи Django или список кандидатов.")
        parser.add_argument("--tmdb-delay", type=float, default=0.6)
        parser.add_argument("--wikidata-delay", type=float, default=1.0)
        parser.add_argument("--sparql-delay", type=float, default=5.0)
        parser.add_argument("--maxlag-wait", type=int, default=1800, help="Бюджет ожидания maxlag для одного запроса, секунды; по умолчанию 30 минут.")

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 10000:
            raise CommandError("--limit должен быть от 1 до 10000.")
        if options["min_votes"] < 0 or options["backfill_limit"] < 0:
            raise CommandError("Количество голосов/обложек не может быть отрицательным.")
        if options["maxlag_wait"] < 0:
            raise CommandError("--maxlag-wait не может быть отрицательным.")
        if options["covers_only"] and options["skip_backfill"]:
            raise CommandError("--covers-only несовместим с --skip-backfill.")
        if any(not math.isfinite(options[key]) or options[key] < minimum for key, minimum in
               (("tmdb_delay", 0.6), ("wikidata_delay", 1.0), ("sparql_delay", 5.0))):
            raise CommandError("Минимальные паузы: TMDB 0.6 с, Wikidata 1 с, SPARQL 5 с.")
        languages = list(dict.fromkeys(x.strip() for x in options["languages"].split(",") if x.strip()))
        if "en" not in languages or any(not re.fullmatch(r"[a-z]{2}", x) for x in languages):
            raise CommandError("Языки: двухбуквенные коды через запятую; en обязателен.")
        if options["without_genres"] and not re.fullmatch(r"\d+(,\d+)*", options["without_genres"]):
            raise CommandError("--without-genres: ID жанров через запятую либо пустая строка.")
        token = clean(os.getenv("TMDB_READ_TOKEN") or getattr(settings, "TMDB_READ_TOKEN", ""))
        api_key = clean(os.getenv("TMDB_API_KEY") or getattr(settings, "TMDB_API_KEY", ""))
        if not token and not api_key:
            raise CommandError("Добавь TMDB_READ_TOKEN (API Read Access Token) или TMDB_API_KEY в .env и запусти снова.")
        directory = Path(options["state_dir"]).expanduser().resolve()
        self.stdout.write("Импортёр написан с помощью ИИ (OpenAI Codex).")
        self.stdout.write(f"State/cache/reports: {directory}. Ctrl+C безопасно останавливает работу.")
        with run_lock(directory), database_lock():
            state = State(directory)
            api = API(state, token, api_key, languages, self.stdout.write, {
                "tmdb": options["tmdb_delay"], "wikidata": options["wikidata_delay"], "sparql": options["sparql_delay"],
            }, maxlag_wait=options["maxlag_wait"])
            try:
                database = settings.DATABASES["default"]
                config = {"version": 1, "database": [connection.vendor, str(database["NAME"]), database.get("HOST", ""), database.get("PORT", "")],
                          "languages": languages, "min_votes": options["min_votes"], "sort": options["sort"],
                          "without_genres": options["without_genres"]}
                previous = state.meta("config")
                if previous and previous != config:
                    raise CommandError("Этот state-dir принадлежит другой БД/выборке/языкам. Укажи новый --state-dir; состояние не удаляй.")
                state.set_meta("config", config)
                if options["refresh_cache"]:
                    state.db.execute("DELETE FROM cache")
                    state.db.commit()
                if options["retry_skipped"]:
                    state.db.execute("UPDATE manifest SET status='pending' WHERE status='skipped'")
                    state.db.execute("DELETE FROM covers WHERE status!='filled'")
                    state.db.commit()
                if options["reprocess"]:
                    state.db.execute("UPDATE manifest SET status='pending' WHERE status IN ('created','updated')")
                    state.db.commit()
                configuration = api.get(TMDB + "/configuration")
                images = configuration.get("images", {}) if configuration else {}
                base = images.get("secure_base_url", "")
                sizes = images.get("poster_sizes", [])
                if not base.startswith("https://image.tmdb.org/") or not sizes:
                    raise CommandError("Не удалось получить корректную конфигурацию изображений TMDB.")
                size = "w500" if "w500" in sizes else sizes[-1]
                self.image_base = base.rstrip("/") + "/" + size
                if not options["skip_backfill"]:
                    self.backfill(api, state, options)
                if not options["covers_only"]:
                    self.discover(api, state, options)
                    self.import_manifest(api, state, options, languages)
                counts = dict(state.db.execute("SELECT status,COUNT(*) FROM manifest GROUP BY status").fetchall())
                self.stdout.write(self.style.SUCCESS("Готово. Состояние списка кандидатов: " + json.dumps(counts, ensure_ascii=False)))
                self.stdout.write("Переводы/связи добавлены только там, где их предоставляют источники. RAFS-оценки не менялись.")
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Остановлено. Повтори ту же команду для продолжения."))
            finally:
                state.report()
                api.session.close()
                state.db.close()

    def poster(self, item):
        path = clean(item.get("poster_path"))
        return self.image_base + path if re.fullmatch(r"/[A-Za-z0-9_.-]+\.(?:jpg|png|webp)", path, re.I) else ""

    def discover(self, api, state, options):
        cutoff = state.meta("release_cutoff") or date.today().isoformat()
        state.set_meta("release_cutoff", cutoff)
        while state.db.execute("SELECT COUNT(*) FROM manifest").fetchone()[0] < options["limit"] and not state.meta("exhausted", False):
            page = state.meta("last_page", 0) + 1
            if page > 500:
                state.set_meta("exhausted", True)
                break
            data = api.get(TMDB + "/discover/movie", {
                "language": "en-US", "sort_by": options["sort"], "page": page,
                "include_adult": "false", "include_video": "false",
                "vote_count.gte": options["min_votes"], "primary_release_date.lte": cutoff,
                "without_genres": options["without_genres"],
            })
            if not data or "results" not in data:
                raise CommandError("TMDB discover не вернул results.")
            with state.db:
                for row in data["results"]:
                    if isinstance(row.get("id"), int) and row["id"] > 0:
                        state.db.execute("INSERT OR IGNORE INTO manifest(tmdb_id) VALUES (?)", (row["id"],))
                state.db.execute("INSERT OR REPLACE INTO meta VALUES ('last_page',?)", (json.dumps(page),))
            if not data["results"] or page >= min(int(data.get("total_pages", page)), 500):
                state.set_meta("exhausted", True)
            if page % 25 == 0 or page == 1:
                self.stdout.write(f"Список: страница {page}, уникальных кандидатов {state.db.execute('SELECT COUNT(*) FROM manifest').fetchone()[0]}.")
        state.report()
        self.stdout.write("Список кандидатов сохранён; повторные запуски используют его, а не новый рейтинг популярности.")

    def import_manifest(self, api, state, options, languages):
        # First N unique candidates; a smaller test limit can later be increased.
        last = state.db.execute("SELECT position FROM manifest ORDER BY position LIMIT 1 OFFSET ?", (options["limit"] - 1,)).fetchone()
        upper = last[0] if last else state.db.execute("SELECT COALESCE(MAX(position),0) FROM manifest").fetchone()[0]
        cursor = 0
        counters = Counter()
        while True:
            rows = state.db.execute("SELECT * FROM manifest WHERE position>? AND position<=? AND status IN ('pending','error') ORDER BY position LIMIT 20", (cursor, upper)).fetchall()
            if not rows:
                break
            details = []
            for row in rows:
                item = api.details(row["tmdb_id"])
                if not item or item.get("adult") or item.get("video"):
                    if not options["dry_run"]:
                        state.mark(row["tmdb_id"], "skipped", reason="TMDB: отсутствует, adult или video.")
                    continue
                if options["without_genres"] and set(map(int, options["without_genres"].split(","))) & {x["id"] for x in item.get("genres", [])}:
                    if not options["dry_run"]:
                        state.mark(row["tmdb_id"], "skipped", reason="Исключённый жанр.")
                    continue
                if item.get("id") != row["tmdb_id"]:
                    raise CommandError("TMDB details вернул неожиданный ID.")
                details.append(item)
            mapping = api.resolve(details)
            entities = api.entities(mapping.values(), claims=True)
            related_qids = {"Q11424"}
            for entity in entities.values():
                related_qids.update(claim_qids(entity, ("P31",)))
                for _, props in RELATIONS.values():
                    related_qids.update(claim_qids(entity, props))
            related = api.entities(related_qids) if details else {}
            for item in details:
                try:
                    original_qid = mapping.get(item["id"])
                    if not original_qid:
                        raise ImportIssue("Нет однозначного соответствия Wikidata; фильм не создан.")
                    obj, created = import_one(item, original_qid, entities.get(original_qid, {}), related, languages, self.poster(item), options["dry_run"])
                    status = "created" if created else "updated"
                    counters[status] += 1
                    if not options["dry_run"]:
                        state.mark(item["id"], status, obj.pk)
                    self.stdout.write(f"{'DRY RUN ' if options['dry_run'] else ''}{status}: TMDB {item['id']} / {original_qid} / {clean(item.get('title'))}")
                except ImportIssue as error:
                    counters["skipped"] += 1
                    if not options["dry_run"]:
                        state.mark(item["id"], "skipped", reason=str(error))
                    self.stdout.write(self.style.WARNING(f"Пропуск TMDB {item['id']}: {error}"))
                except Exception as error:
                    # Stop on unexpected DB/programming failures instead of hiding them.
                    if not options["dry_run"]:
                        state.mark(item["id"], "error", reason=type(error).__name__)
                    raise CommandError(f"Ошибка {type(error).__name__} на TMDB {item['id']}; транзакция фильма отменена, прогресс сохранён.") from error
            cursor = rows[-1]["position"]
            state.report()
        self.stdout.write("За этот запуск: " + json.dumps(counters, ensure_ascii=False))

    def backfill(self, api, state, options):
        checked = 0
        movies = Movie.objects.filter(Q(cover_url="") | Q(cover_url__isnull=True)).order_by("pk")
        for movie in movies.iterator(chunk_size=100):
            if movie.cover and movie.cover.storage.exists(movie.cover.name):
                continue
            previous = state.db.execute("SELECT status FROM covers WHERE movie_pk=?", (movie.pk,)).fetchone()
            if previous and previous[0] in {"not_found", "ambiguous"} and not options["retry_skipped"]:
                continue
            if options["backfill_limit"] and checked >= options["backfill_limit"]:
                break
            checked += 1
            try:
                candidates = set()
                for identifier, source, pattern in ((clean(movie.wikidata_id), "wikidata_id", QID), (clean(movie.imdb_id), "imdb_id", IMDB)):
                    if not pattern.fullmatch(identifier):
                        continue
                    payload = api.get(f"{TMDB}/find/{identifier}", {"external_source": source, "language": "en-US"}) or {}
                    candidates.update(row["id"] for row in payload.get("movie_results", []))
                if len(candidates) > 1:
                    raise ImportIssue("Wikidata/IMDb дали несколько разных фильмов TMDB.")
                if not candidates:
                    if not options["dry_run"]:
                        state.cover_mark(movie.pk, "not_found", "Нет ID либо точного совпадения TMDB; поиск по названию отключён.")
                    continue
                tmdb_id = next(iter(candidates))
                item = api.details(tmdb_id) or {}
                ext = item.get("external_ids", {})
                if movie.imdb_id and ext.get("imdb_id") and movie.imdb_id != ext["imdb_id"]:
                    raise ImportIssue("IMDb существующего фильма и TMDB отличаются.")
                if movie.wikidata_id and ext.get("wikidata_id") and movie.wikidata_id != ext["wikidata_id"]:
                    raise ImportIssue("Wikidata существующего фильма и TMDB отличаются; возможно перенаправление, проверь вручную.")
                url = self.poster(item)
                if not url:
                    if not options["dry_run"]:
                        state.cover_mark(movie.pk, "not_found", "У TMDB нет постера.")
                    continue
                if not options["dry_run"]:
                    with transaction.atomic():
                        current = Movie.objects.select_for_update().get(pk=movie.pk)
                        if current.cover_url or (current.cover and current.cover.storage.exists(current.cover.name)):
                            continue
                        current.cover_url = url
                        current.save(update_fields=["cover_url"])
                    state.cover_mark(movie.pk, "filled")
                self.stdout.write(f"{'DRY RUN ' if options['dry_run'] else ''}Обложка: movie #{movie.pk} <- TMDB {tmdb_id}")
            except ImportIssue as error:
                if not options["dry_run"]:
                    state.cover_mark(movie.pk, "ambiguous", str(error))
                self.stdout.write(self.style.WARNING(f"Обложка #{movie.pk}: {error}"))
        self.stdout.write(f"Проверено существующих фильмов без обложки: {checked}.")
