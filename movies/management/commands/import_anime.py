"""Conservative, resumable anime import. Написан с помощью ИИ (OpenAI Codex).

TMDB's exact anime keyword AND Animation genre are discovery evidence, not a
claim of completeness. Wikidata P31/P279 must independently confirm the format.
HTTP/cache/retries/maxlag, identity checks and fill-only writes are shared with
import_popular_movies. See README_import_anime.md for sources and limitations.
"""

import csv
import json
import math
import os
import sqlite3
from collections import Counter
from itertools import zip_longest
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError
from django.db import connection

from .import_popular_movies import (
    API, IMDB, MEDIA_FIELDS, QID, REGIONS, RELATIONS, TMDB, ImportIssue,
    State, Command as MovieCommand, claim_qids, claim_values, clean,
    database_lock, import_one, run_lock,
)

ANIME_KEYWORD = 210024  # Verified /search/keyword + /keyword/210024: "anime".
ANIMATION_GENRE = 16
FORMAT_ROOTS = {"movie": {"Q11424"}, "tv": {"Q5398426", "Q526877"}}
PART_TYPES = {"Q3464665", "Q21191270"}  # TV season / TV episode, never works to import.
FORMAT_MAX_DEPTH = 64
FORMAT_MAX_CLASSES = 2048


def check_state_directory(directory):
    """Reject the old movie manifest read-only, before even touching its lock."""
    path = Path(directory) / "state.sqlite3"
    if not path.exists():
        return
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(manifest)")}
        if columns and "media_type" not in columns:
            raise CommandError("Это состояние import_popular_movies. Укажи отдельный --state-dir для аниме.")


class AnimeState(State):
    """Separate manifest: movie/123 and tv/123 are independent candidates."""

    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        check_state_directory(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.directory / "state.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS manifest (
                position INTEGER PRIMARY KEY AUTOINCREMENT,
                media_type TEXT NOT NULL CHECK (media_type IN ('movie','tv')),
                tmdb_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', movie_pk INTEGER,
                reason TEXT NOT NULL DEFAULT '', dry_status TEXT NOT NULL DEFAULT '',
                dry_reason TEXT NOT NULL DEFAULT '', UNIQUE(media_type, tmdb_id)
            );
        """)
        self.db.commit()

    def mark(self, media_type, tmdb_id, status, movie_pk=None, reason="", *, dry_run=False):
        if dry_run:
            self.db.execute("UPDATE manifest SET dry_status=?,dry_reason=? WHERE media_type=? AND tmdb_id=?",
                            (status, reason, media_type, tmdb_id))
        else:
            self.db.execute("UPDATE manifest SET status=?,movie_pk=?,reason=? WHERE media_type=? AND tmdb_id=?",
                            (status, movie_pk, reason, media_type, tmdb_id))
        self.db.commit()

    def report(self):
        cursor = self.db.execute("SELECT * FROM manifest ORDER BY position")
        with (self.directory / "import_report.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow([column[0] for column in cursor.description])
            writer.writerows(cursor)


class AnimeAPI(API):
    def details(self, media_type, tmdb_id):
        if media_type not in MEDIA_FIELDS:
            raise ValueError("Unsupported media type")
        return self.get(f"{TMDB}/{media_type}/{tmdb_id}", {
            "language": "en-US", "append_to_response": "external_ids,translations,keywords",
        })


def validate_candidate(item, media_type, tmdb_id, min_votes):
    if not item:
        raise ImportIssue("TMDB: произведение отсутствует.")
    if item.get("id") != tmdb_id:
        raise CommandError("TMDB details вернул неожиданный ID; импорт остановлен.")
    if item.get("adult") or item.get("video"):
        raise ImportIssue("TMDB: adult или video.")
    if ANIMATION_GENRE not in {row.get("id") for row in item.get("genres", [])}:
        raise ImportIssue("Нет подтверждённого жанра Animation в TMDB details.")
    # The wrappers differ: movie.keywords.keywords vs tv.keywords.results.
    key = "keywords" if media_type == "movie" else "results"
    keywords = item.get("keywords", {}).get(key, [])
    if ANIME_KEYWORD not in {row.get("id") for row in keywords}:
        raise ImportIssue("Нет точной метки anime (210024) в TMDB details.")
    if (item.get("vote_count") or 0) < min_votes:
        raise ImportIssue("Число голосов ниже --min-votes.")


def confirmed_format(entity, media_type, api):
    """Confirm a direct P31 using the complete bounded P279 ancestry.

    Anime types can reach film/series quickly while another inheritance branch
    goes through animation, art, works and abstract classes. Eight edges was
    too small for that complete graph. Keep checking every branch for conflicting
    formats and parts, but allow a deeper graph and reuse class data across the
    sequential run. A missing or truncated graph still never counts as proof.
    """
    direct = set(claim_qids(entity, ("P31",)))
    if not direct:
        raise ImportIssue("Wikidata: нет P31 для подтверждения формата произведения.")
    roots = set().union(*FORMAT_ROOTS.values()) | PART_TYPES
    # Class relationships are public source data, not a per-title verdict.
    # Reusing them avoids repeated API/cache decoding for shared ancestors.
    cache = getattr(api, "_anime_format_graph", None)
    if not isinstance(cache, dict):
        cache = {}
        api._anime_format_graph = cache

    graph, frontier, depth = {}, direct.copy(), 0
    while frontier:
        if depth > FORMAT_MAX_DEPTH:
            raise ImportIssue(
                f"Иерархия P31/P279 глубже {FORMAT_MAX_DEPTH} переходов; "
                "формат не подтверждён."
            )
        if len(graph) + len(frontier) > FORMAT_MAX_CLASSES:
            raise ImportIssue(
                f"Иерархия P31/P279 содержит больше {FORMAT_MAX_CLASSES} классов; "
                "нужен ручной разбор типа."
            )
        missing = frontier - roots - cache.keys()
        data = api.entities(sorted(missing), claims=True) if missing else {}
        for qid in sorted(frontier):
            if qid in roots:
                graph[qid] = set()
            else:
                if qid not in cache:
                    value = data.get(qid, {})
                    if not value or "missing" in value:
                        raise ImportIssue(f"Wikidata: класс {qid} недоступен; формат не подтверждён.")
                    cache[qid] = frozenset(claim_qids(value, ("P279",)))
                graph[qid] = set(cache[qid])
        frontier = set().union(*(graph[qid] for qid in frontier)) - graph.keys()
        depth += 1

    def ancestors(qid):
        seen, pending = set(), {qid}
        while pending:
            current = pending.pop()
            if current not in seen:
                seen.add(current)
                pending.update(graph.get(current, set()) - seen)
        return seen

    paths = {qid: ancestors(qid) for qid in direct}
    all_ancestors = set().union(*paths.values())
    if all_ancestors & PART_TYPES:
        raise ImportIssue("Wikidata описывает отдельный сезон или эпизод, а не целое произведение.")
    other = "tv" if media_type == "movie" else "movie"
    if all_ancestors & FORMAT_ROOTS[other]:
        raise ImportIssue("Формат Wikidata противоречит источнику TMDB movie/tv.")
    matches = {qid for qid, path in paths.items() if path & FORMAT_ROOTS[media_type]}
    # Keep the most specific direct type; unrelated competing types are ambiguous.
    specific = {qid for qid in matches if not any(qid in paths[other] for other in matches - {qid})}
    if len(specific) != 1:
        raise ImportIssue("Нет однозначного подтверждённого типа фильма/сериала в P31/P279.")
    return specific.pop()


def validate_identity(entity, item, media_type):
    """Stricter ambiguity gate; shared import_one still checks exact ID matches."""
    if not QID.fullmatch(clean(entity.get("id"))) or "missing" in entity:
        raise ImportIssue("Wikidata entity отсутствует.")
    prop = MEDIA_FIELDS[media_type][2]
    ids = {clean(value) for value in claim_values(entity, prop)}
    imdbs = {value for value in claim_values(entity, "P345") if isinstance(value, str) and IMDB.fullmatch(value)}
    if len(ids) > 1 or len(imdbs) > 1:
        raise ImportIssue("Неоднозначная идентичность: несколько TMDB/IMDb ID в Wikidata.")
    if ids and ids != {str(item["id"])}:
        raise ImportIssue(f"TMDB ID не совпадает с Wikidata {prop}.")


class Command(MovieCommand):
    help = (
        "Импорт аниме-фильмов и целых сериалов: Animation AND точный keyword anime; "
        "формат и идентичность подтверждаются Wikidata. Не все существующие аниме. "
        "Написан с помощью ИИ (OpenAI Codex)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--media-type", choices=["movie", "tv", "both"], default="both")
        parser.add_argument("--limit", type=int, default=10000,
                            help="Всего кандидатов, включая пропуски: до 10000 на источник, до 20000 для both.")
        parser.add_argument("--min-votes", type=int, default=0,
                            help="По умолчанию 0. Порог 50 исключает многие редкие и малооценённые аниме.")
        parser.add_argument("--languages", default="en,ru,uk,kk,es,de")
        parser.add_argument("--sort", choices=["popularity.desc", "vote_count.desc"], default="popularity.desc")
        parser.add_argument("--state-dir", default=str(Path(settings.BASE_DIR) / ".rafs_import" / "anime"))
        parser.add_argument("--dry-run", action="store_true",
                            help="Без записей в Django БД; сохраняются API-кеш, кандидаты и dry_status в CSV.")
        parser.add_argument("--retry-skipped", action="store_true", help="Повторить пропуски после ручной проверки.")
        parser.add_argument("--reprocess", action="store_true", help="Повторить обработанные записи, заполняя только пустые поля.")
        parser.add_argument("--refresh-cache", action="store_true", help="Очистить только API-кеш этого импорта.")
        parser.add_argument("--tmdb-delay", type=float, default=0.6)
        parser.add_argument("--wikidata-delay", type=float, default=1.0)
        parser.add_argument("--sparql-delay", type=float, default=5.0)
        parser.add_argument("--maxlag-wait", type=int, default=1800,
                            help="Бюджет ожидания maxlag на запрос, секунды. maxlag=5 не отключается.")

    def handle(self, *args, **options):
        maximum = 20000 if options["media_type"] == "both" else 10000
        if not 1 <= options["limit"] <= maximum:
            raise CommandError(f"--limit должен быть от 1 до {maximum}.")
        if options["min_votes"] < 0 or options["maxlag_wait"] < 0:
            raise CommandError("--min-votes и --maxlag-wait не могут быть отрицательными.")
        if any(not math.isfinite(options[key]) or options[key] < minimum for key, minimum in
               (("tmdb_delay", 0.6), ("wikidata_delay", 1.0), ("sparql_delay", 5.0))):
            raise CommandError("Минимальные паузы: TMDB 0.6 с, Wikidata 1 с, SPARQL 5 с.")
        languages = list(dict.fromkeys(x.strip() for x in options["languages"].split(",") if x.strip()))
        if "en" not in languages or set(languages) - REGIONS.keys():
            raise CommandError("Поддерживаются en,ru,uk,kk,es,de; en обязателен.")
        token = clean(os.getenv("TMDB_READ_TOKEN") or getattr(settings, "TMDB_READ_TOKEN", ""))
        api_key = clean(os.getenv("TMDB_API_KEY") or getattr(settings, "TMDB_API_KEY", ""))
        if not token and not api_key:
            raise CommandError("Нужен TMDB_READ_TOKEN или TMDB_API_KEY в .env.")
        directory = Path(options["state_dir"]).expanduser().resolve()
        check_state_directory(directory)
        self.stdout.write("Импортёр написан с помощью ИИ (OpenAI Codex).")
        self.stdout.write(f"State/cache/report: {directory}. Ctrl+C сохраняет прогресс.")
        # Also serialize anime runs using different state directories on SQLite.
        # PostgreSQL's shared advisory lock serializes with import_popular_movies.
        with run_lock(directory), run_lock(Path(settings.BASE_DIR) / ".rafs_import" / "anime-runs"), database_lock():
            state = AnimeState(directory)
            api = AnimeAPI(state, token, api_key, languages, self.stdout.write, {
                "tmdb": options["tmdb_delay"], "wikidata": options["wikidata_delay"], "sparql": options["sparql_delay"],
            }, maxlag_wait=options["maxlag_wait"])
            try:
                database = settings.DATABASES["default"]
                config = {
                    "importer": "anime-v1", "keyword": ANIME_KEYWORD, "genre": ANIMATION_GENRE,
                    "database": [connection.vendor, str(database["NAME"]), database.get("HOST", ""), database.get("PORT", "")],
                    "media_type": options["media_type"], "languages": languages,
                    "min_votes": options["min_votes"], "sort": options["sort"],
                }
                previous = state.meta("config")
                if previous and previous != config:
                    raise CommandError("State-dir принадлежит другой БД/выборке/языкам; укажи новый --state-dir.")
                state.set_meta("config", config)
                with state.db:
                    if options["refresh_cache"]:
                        state.db.execute("DELETE FROM cache")
                    if options["retry_skipped"] and not options["dry_run"]:
                        state.db.execute("UPDATE manifest SET status='pending' WHERE status='skipped'")
                    if options["reprocess"] and not options["dry_run"]:
                        state.db.execute("UPDATE manifest SET status='pending' WHERE status IN ('created','updated')")
                keyword = api.get(f"{TMDB}/keyword/{ANIME_KEYWORD}")
                if not keyword or keyword.get("id") != ANIME_KEYWORD or keyword.get("name") != "anime":
                    raise CommandError("TMDB больше не подтверждает keyword 210024 = anime; автоматический отбор остановлен.")
                configuration = api.get(TMDB + "/configuration")
                images = configuration.get("images", {}) if configuration else {}
                base, sizes = images.get("secure_base_url", ""), images.get("poster_sizes", [])
                if not base.startswith("https://image.tmdb.org/") or not sizes:
                    raise CommandError("Не удалось получить корректную конфигурацию изображений TMDB.")
                self.image_base = base.rstrip("/") + "/" + ("w500" if "w500" in sizes else sizes[-1])
                self.discover(api, state, options)
                self.import_manifest(api, state, options, languages)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("Остановлено. Повтори ту же команду для продолжения."))
            finally:
                state.report()
                api.session.close()
                state.db.close()

    def discover(self, api, state, options):
        media_types = ["movie", "tv"] if options["media_type"] == "both" else [options["media_type"]]
        while state.db.execute("SELECT COUNT(*) FROM manifest").fetchone()[0] < options["limit"]:
            pages = {}
            for media_type in media_types:
                if state.meta(f"exhausted:{media_type}", False):
                    continue
                page = state.meta(f"page:{media_type}", 0) + 1
                params = {
                    "language": "en-US", "sort_by": options["sort"], "page": page,
                    "include_adult": "false", "with_genres": str(ANIMATION_GENRE),
                    "with_keywords": str(ANIME_KEYWORD), "vote_count.gte": options["min_votes"],
                }
                if media_type == "movie":
                    params["include_video"] = "false"
                else:
                    params["include_null_first_air_dates"] = "true"
                data = api.get(f"{TMDB}/discover/{media_type}", params)
                if not data or not isinstance(data.get("results"), list):
                    raise CommandError(f"TMDB discover/{media_type} не вернул results.")
                pages[media_type] = (page, data)
            if not pages:
                break
            # Commit IDs AND cursors together. Interleave sources so a 20-item
            # dry-run exercises both, rather than exhausting movies first.
            with state.db:
                streams = [[(media, row) for row in data["results"]] for media, (_, data) in pages.items()]
                for group in zip_longest(*streams):
                    for candidate in group:
                        if candidate:
                            media_type, row = candidate
                            if type(row.get("id")) is int and row["id"] > 0:
                                state.db.execute("INSERT OR IGNORE INTO manifest(media_type,tmdb_id) VALUES (?,?)",
                                                 (media_type, row["id"]))
                for media_type, (page, data) in pages.items():
                    for key, value in (
                        (f"page:{media_type}", page),
                        (f"exhausted:{media_type}", not data["results"] or page >= min(int(data.get("total_pages", page)), 500)),
                    ):
                        state.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value)))
            self.stdout.write(f"Список: {state.db.execute('SELECT COUNT(*) FROM manifest').fetchone()[0]} уникальных кандидатов.")

    def import_manifest(self, api, state, options, languages):
        last = state.db.execute("SELECT position FROM manifest ORDER BY position LIMIT 1 OFFSET ?", (options["limit"] - 1,)).fetchone()
        upper = last[0] if last else state.db.execute("SELECT COALESCE(MAX(position),0) FROM manifest").fetchone()[0]
        cursor, counts = 0, Counter()
        while True:
            status_filter = "" if options["dry_run"] else "AND status IN ('pending','error')"
            rows = state.db.execute(
                f"SELECT * FROM manifest WHERE position>? AND position<=? {status_filter} ORDER BY position LIMIT 20",
                (cursor, upper),
            ).fetchall()
            if not rows:
                break
            for row in rows:
                media_type, tmdb_id = row["media_type"], row["tmdb_id"]
                try:
                    item = api.details(media_type, tmdb_id)
                    validate_candidate(item, media_type, tmdb_id, options["min_votes"])
                    qid = api.resolve([item], media_type=media_type).get(tmdb_id)
                    if not qid:
                        raise ImportIssue("Нет однозначного соответствия Wikidata по ID; запись не создана.")
                    entity = api.entities([qid], claims=True).get(qid, {})
                    validate_identity(entity, item, media_type)
                    type_qid = confirmed_format(entity, media_type, api)
                    related_qids = {type_qid}
                    for _, props in RELATIONS.values():
                        related_qids.update(claim_qids(entity, props))
                    related = api.entities(related_qids)
                    obj, created = import_one(
                        item, qid, entity, related, languages, self.poster(item), options["dry_run"],
                        media_type=media_type, confirmed_type=type_qid,
                    )
                    status = "created" if created else "updated"
                    state.mark(media_type, tmdb_id, status, obj.pk if obj else None, dry_run=options["dry_run"])
                    counts[status] += 1
                    self.stdout.write(f"{'DRY RUN ' if options['dry_run'] else ''}{status}: {media_type}/{tmdb_id}, {qid}")
                except ImportIssue as error:
                    state.mark(media_type, tmdb_id, "skipped", reason=str(error), dry_run=options["dry_run"])
                    counts["skipped"] += 1
                    self.stdout.write(self.style.WARNING(f"Пропуск {media_type}/{tmdb_id}: {error}"))
                except CommandError:
                    raise
                except Exception as error:
                    state.mark(media_type, tmdb_id, "error", reason=type(error).__name__, dry_run=options["dry_run"])
                    raise CommandError(
                        f"Ошибка {type(error).__name__} на {media_type}/{tmdb_id}; транзакция отменена, прогресс сохранён."
                    ) from error
            cursor = rows[-1]["position"]
            state.report()
        self.stdout.write("За этот запуск: " + json.dumps(counts, ensure_ascii=False))

