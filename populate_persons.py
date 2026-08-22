"""One-time seeder for people credited in popular films and TV series.

Run from the Rafs project root after the Person.name JSONField migration:

    python populate_persons.py

Small test run (also removes the previous off-topic seed):

    python populate_persons.py --works 100 --limit 100 --clear

The default run scans 1,000 popular works and saves up to 3,000 people.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from collections import defaultdict
from collections.abc import Iterable

import django
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from movies.movie_models import Person  # noqa: E402


WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIDATA_ACTION_API_URL = "https://www.wikidata.org/w/api.php"

LANGUAGES = ("ru", "en", "uk", "kk", "es")
DEFAULT_PERSON_LIMIT = 3_000
DEFAULT_WORK_LIMIT = 1_000
ACTION_API_CHUNK_SIZE = 50
SPARQL_VALUES_CHUNK_SIZE = 250
REQUEST_DELAY_SECONDS = 1.0
MAX_API_ATTEMPTS = 6
MIN_WORK_SITELINKS = 25
WORK_CANDIDATE_MULTIPLIER = 4

# Exact P31 values deliberately avoid a global P279* traversal. For this seed
# we prefer a reliable, relevant sample over an exhaustive ontology walk.
WORK_TYPES = (
    ("фильмов", "Q11424", 0.7),
    ("сериалов", "Q5398426", 0.3),
)

# Movie/series credit properties used by Movie.parse_movie_details.
CREDIT_PROPERTIES = (
    "P57",   # director
    "P58",   # screenwriter
    "P161",  # cast member
    "P162",  # producer
    "P86",   # composer
    "P725",  # voice actor
)

USER_AGENT = (
    "RafsWikidataBot/0.1 "
    "(contact: kislyakhelp@gmail.com; "
    "https://github.com/ivanKislyak/Rafs)"
)

RETRYABLE_API_ERRORS = {
    "maxlag",
    "ratelimited",
    "readonly",
    "internal_api_error_DBQueryError",
}


def build_work_candidates_query(type_qid: str, limit: int) -> str:
    """Return a bounded unsorted pool for one exact work type.

    Sorting is intentionally done in Python. ORDER BY over all films/series
    makes WDQS build and sort the full result before applying LIMIT.
    """

    return f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wikibase: <http://wikiba.se/ontology#>

SELECT ?work ?sitelinks WHERE {{
  ?work wdt:P31 wd:{type_qid};
        wikibase:sitelinks ?sitelinks.

  FILTER(?sitelinks >= {MIN_WORK_SITELINKS})
}}
LIMIT {limit}
"""


def build_human_validation_query(qids: list[str]) -> str:
    """Validate exact candidate QIDs as humans and get popularity metadata."""

    values = " ".join(f"wd:{qid}" for qid in qids)
    return f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wikibase: <http://wikiba.se/ontology#>

SELECT ?person ?sitelinks WHERE {{
  VALUES ?person {{ {values} }}
  ?person wdt:P31 wd:Q5.
  OPTIONAL {{ ?person wikibase:sitelinks ?sitelinks. }}
}}
"""


def build_session() -> requests.Session:
    retry = Retry(
        total=6,
        connect=6,
        read=6,
        status=6,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "gzip, deflate",
        }
    )
    return session


def request_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, object],
    timeout: tuple[int, int],
    accept: str,
) -> dict:
    """GET JSON with HTTP retries plus MediaWiki API-error backoff."""

    for attempt in range(1, MAX_API_ATTEMPTS + 1):
        response = session.get(
            url,
            params=params,
            timeout=timeout,
            headers={"Accept": accept},
        )
        response.raise_for_status()
        payload = response.json()

        error = payload.get("error")
        if not error:
            return payload

        error_code = error.get("code", "unknown")
        if error_code not in RETRYABLE_API_ERRORS or attempt == MAX_API_ATTEMPTS:
            raise RuntimeError(
                f"Wikidata API error {error_code}: {error.get('info', error)}"
            )

        wait_seconds = min(60, 2**attempt)
        print(
            f"Wikidata временно ответила {error_code}. "
            f"Повтор через {wait_seconds} сек. ({attempt}/{MAX_API_ATTEMPTS})"
        )
        time.sleep(wait_seconds)

    raise RuntimeError("Wikidata request failed after all retries")


def chunked(items: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def fetch_work_candidates(
    session: requests.Session,
    *,
    type_qid: str,
    query_limit: int,
) -> dict[str, int]:
    """Fetch one bounded pool and return QID -> sitelink count."""

    payload = request_json(
        session,
        WIKIDATA_SPARQL_URL,
        params={
            "query": build_work_candidates_query(type_qid, query_limit),
            "format": "json",
        },
        timeout=(15, 90),
        accept="application/sparql-results+json",
    )

    candidates: dict[str, int] = {}

    for item in payload.get("results", {}).get("bindings", []):
        entity_url = item.get("work", {}).get("value", "")
        qid = entity_url.rsplit("/", 1)[-1]
        if not (qid.startswith("Q") and qid[1:].isdigit()):
            continue

        raw_sitelinks = item.get("sitelinks", {}).get("value", "0")
        try:
            sitelinks = int(raw_sitelinks)
        except (TypeError, ValueError):
            sitelinks = 0
        candidates[qid] = max(candidates.get(qid, 0), sitelinks)

    return candidates


def fetch_popular_work_qids(
    session: requests.Session,
    work_limit: int,
) -> list[str]:
    """Fetch films and series separately, then rank the bounded pools locally."""

    print(f"Ищем {work_limit} популярных фильмов и сериалов...")
    targets = [
        round(work_limit * WORK_TYPES[0][2]),
        work_limit - round(work_limit * WORK_TYPES[0][2]),
    ]
    if work_limit == 1:
        targets = [1, 0]

    all_candidates: dict[str, int] = {}
    selected: set[str] = set()

    for index, ((label, type_qid, _), target) in enumerate(
        zip(WORK_TYPES, targets, strict=True),
        start=1,
    ):
        if target == 0:
            continue

        query_limit = min(
            5_000,
            max(target * WORK_CANDIDATE_MULTIPLIER, target + 100),
        )
        print(
            f"Получаем ограниченную выборку {label}: "
            f"до {query_limit} кандидатов без глобальной сортировки..."
        )
        candidates = fetch_work_candidates(
            session,
            type_qid=type_qid,
            query_limit=query_limit,
        )
        all_candidates.update(candidates)

        ranked_for_type = sorted(
            candidates,
            key=lambda qid: (-candidates[qid], qid),
        )
        selected.update(ranked_for_type[:target])
        print(f"Кандидатов {label} получено: {len(candidates)}")

        if index < len(WORK_TYPES):
            time.sleep(REQUEST_DELAY_SECONDS)

    # If one type returned too few rows, fill the remainder from the other pool.
    if len(selected) < work_limit:
        for qid in sorted(
            all_candidates,
            key=lambda item_qid: (-all_candidates[item_qid], item_qid),
        ):
            selected.add(qid)
            if len(selected) >= work_limit:
                break

    qids = sorted(
        selected,
        key=lambda qid: (-all_candidates[qid], qid),
    )[:work_limit]

    if not qids:
        raise RuntimeError("Wikidata Query Service не вернула фильмы или сериалы")

    print(f"Произведений выбрано: {len(qids)}")
    return qids


def extract_credit_qids(entity: dict) -> set[str]:
    """Extract QIDs from the six supported movie credit properties."""

    result: set[str] = set()
    claims = entity.get("claims", {})

    for property_id in CREDIT_PROPERTIES:
        for claim in claims.get(property_id, []):
            if claim.get("rank") == "deprecated":
                continue

            qid = (
                claim.get("mainsnak", {})
                .get("datavalue", {})
                .get("value", {})
                .get("id")
            )
            if isinstance(qid, str) and qid.startswith("Q") and qid[1:].isdigit():
                result.add(qid)

    return result


def collect_credit_scores(
    session: requests.Session,
    work_qids: list[str],
) -> dict[str, float]:
    """Score people by appearances in the most popular works."""

    scores: dict[str, float] = defaultdict(float)
    chunks = list(chunked(work_qids, ACTION_API_CHUNK_SIZE))
    work_rank = {qid: rank for rank, qid in enumerate(work_qids, start=1)}

    print("Загружаем титры этих произведений...")
    for index, qid_chunk in enumerate(chunks, start=1):
        payload = request_json(
            session,
            WIKIDATA_ACTION_API_URL,
            params={
                "action": "wbgetentities",
                "ids": "|".join(qid_chunk),
                "props": "claims",
                "format": "json",
                "maxlag": 5,
            },
            timeout=(10, 90),
            accept="application/json",
        )

        for qid, entity in payload.get("entities", {}).items():
            if entity.get("missing") is not None:
                continue

            rank = work_rank.get(qid, len(work_qids))
            # Top-ranked works count more, but repeated credits also accumulate.
            weight = 1.0 / math.log2(rank + 1)
            for person_qid in extract_credit_qids(entity):
                scores[person_qid] += weight

        print(
            f"Титры: пачка {index}/{len(chunks)}. "
            f"Уникальных кандидатов: {len(scores)}"
        )
        if index < len(chunks):
            time.sleep(REQUEST_DELAY_SECONDS)

    if not scores:
        raise RuntimeError("В выбранных фильмах и сериалах не найдены титры")

    return dict(scores)


def fetch_human_sitelinks(
    session: requests.Session,
    qids: list[str],
) -> dict[str, int]:
    payload = request_json(
        session,
        WIKIDATA_SPARQL_URL,
        params={"query": build_human_validation_query(qids), "format": "json"},
        timeout=(15, 90),
        accept="application/sparql-results+json",
    )

    result: dict[str, int] = {}
    for item in payload.get("results", {}).get("bindings", []):
        entity_url = item.get("person", {}).get("value", "")
        qid = entity_url.rsplit("/", 1)[-1]
        if not (qid.startswith("Q") and qid[1:].isdigit()):
            continue

        raw_sitelinks = item.get("sitelinks", {}).get("value", "0")
        try:
            result[qid] = int(raw_sitelinks)
        except (TypeError, ValueError):
            result[qid] = 0

    return result


def select_people(
    session: requests.Session,
    scores: dict[str, float],
    person_limit: int,
) -> list[str]:
    """Keep only humans and rank them by film relevance and sitelinks."""

    ranked_candidates = sorted(scores, key=lambda qid: (-scores[qid], qid))
    validation_chunks = list(chunked(ranked_candidates, SPARQL_VALUES_CHUNK_SIZE))
    validated: dict[str, int] = {}
    # A margin makes the sitelink tie-break useful near the final cutoff.
    validation_target = min(
        len(ranked_candidates),
        person_limit + max(250, person_limit // 10),
    )

    print("Проверяем, что кандидаты действительно являются людьми...")
    for index, qid_chunk in enumerate(validation_chunks, start=1):
        validated.update(fetch_human_sitelinks(session, qid_chunk))
        print(
            f"Проверка: пачка {index}/{len(validation_chunks)}. "
            f"Людей подтверждено: {len(validated)}"
        )

        if len(validated) >= validation_target:
            break
        time.sleep(REQUEST_DELAY_SECONDS)

    selected = sorted(
        validated,
        key=lambda qid: (-scores[qid], -validated[qid], qid),
    )[:person_limit]

    if not selected:
        raise RuntimeError("После проверки Q5 не осталось ни одной персоны")
    if len(selected) < person_limit:
        print(
            f"Предупреждение: получилось только {len(selected)} людей "
            f"из запрошенных {person_limit}. Увеличь --works."
        )

    print(f"Для сохранения выбрано: {len(selected)} персон")
    return selected


def fetch_labels(
    session: requests.Session,
    qids: list[str],
) -> dict[str, dict[str, str]]:
    payload = request_json(
        session,
        WIKIDATA_ACTION_API_URL,
        params={
            "action": "wbgetentities",
            "ids": "|".join(qids),
            "props": "labels",
            "languages": "|".join(LANGUAGES),
            "format": "json",
            "maxlag": 5,
        },
        timeout=(10, 60),
        accept="application/json",
    )

    result: dict[str, dict[str, str]] = {}

    for qid, entity in payload.get("entities", {}).items():
        if entity.get("missing") is not None:
            continue

        labels = entity.get("labels", {})
        result[qid] = {
            language: label_data["value"]
            for language, label_data in labels.items()
            if language in LANGUAGES and label_data.get("value")
        }

    return result


def save_persons(labels_by_qid: dict[str, dict[str, str]]) -> int:
    persons = [
        Person(wikidata_id=qid, name=labels)
        for qid, labels in labels_by_qid.items()
    ]

    if not persons:
        return 0

    Person.objects.bulk_create(
        persons,
        update_conflicts=True,
        update_fields=["name"],
        unique_fields=["wikidata_id"],
    )
    return len(persons)


def populate_persons(person_limit: int, work_limit: int, clear: bool) -> None:
    session = build_session()
    try:
        work_qids = fetch_popular_work_qids(session, work_limit)
        scores = collect_credit_scores(session, work_qids)
        person_qids = select_people(session, scores, person_limit)
        chunks = list(chunked(person_qids, ACTION_API_CHUNK_SIZE))
        all_labels: dict[str, dict[str, str]] = {}

        print("Загружаем локализованные имена...")
        for index, qid_chunk in enumerate(chunks, start=1):
            all_labels.update(fetch_labels(session, qid_chunk))

            print(
                f"Имена: пачка {index}/{len(chunks)}. "
                f"Получено: {len(all_labels)}/{len(person_qids)}"
            )

            if index < len(chunks):
                time.sleep(REQUEST_DELAY_SECONDS)

        # Destructive DB work happens only after every network stage succeeds.
        if clear:
            print(
                "Удаляем существующие Person и их связи с фильмами "
                "(--clear был указан явно)..."
            )
            deleted_total, _ = Person.objects.all().delete()
            print(f"Удалено связанных строк: {deleted_total}")

        processed = 0
        label_qids = list(all_labels)
        for qid_chunk in chunked(label_qids, ACTION_API_CHUNK_SIZE):
            processed += save_persons(
                {qid: all_labels[qid] for qid in qid_chunk}
            )

        print(
            f"Готово. В этой загрузке обработано {processed} персон. "
            f"Всего Person в БД: {Person.objects.count()}"
        )
    finally:
        session.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Populate Rafs Person rows from credits of popular films and TV series."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_PERSON_LIMIT,
        help=f"Количество персон (по умолчанию: {DEFAULT_PERSON_LIMIT})",
    )
    parser.add_argument(
        "--works",
        type=int,
        default=DEFAULT_WORK_LIMIT,
        help=(
            "Сколько популярных фильмов/сериалов просмотреть "
            f"(по умолчанию: {DEFAULT_WORK_LIMIT})"
        ),
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Сначала удалить все Person и их M2M-связи с фильмами",
    )
    args = parser.parse_args()

    if not 1 <= args.limit <= 10_000:
        parser.error("--limit должен быть от 1 до 10000")
    if not 1 <= args.works <= 10_000:
        parser.error("--works должен быть от 1 до 10000")

    return args


if __name__ == "__main__":
    try:
        cli_args = parse_args()
        populate_persons(cli_args.limit, cli_args.works, cli_args.clear)
    except KeyboardInterrupt:
        print("\nОстановлено пользователем. Уже записанные пачки сохранены.")
        sys.exit(130)
    except Exception as error:
        print(f"\nЗагрузка остановлена: {error}", file=sys.stderr)
        print("Исправь причину и запусти файл снова: существующие QID обновятся.")
        sys.exit(1)