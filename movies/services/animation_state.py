"""Animation campaign manifest. Written with AI assistance (OpenAI Codex).

SQLite owns discovery cursors, cache, results and the practical creation count.
Movie writes commit separately; a crash between the two stores may undercount.
"""

import csv
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import date, timedelta
from itertools import zip_longest
from pathlib import Path

from django.core.management.base import CommandError

from movies.management.commands.import_popular_movies import State

IMPORTER = "animation-v2"
SCHEMA_VERSION = 2
MAX_PAGES = 500


def saved_config(directory):
    """Inspect read-only, before touching a foreign manifest or even its lock."""
    path = Path(directory).resolve() / "state.sqlite3"
    if not path.exists() or not path.stat().st_size:
        return None
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not tables:
                return None  # Interrupted initialization, no campaign could have committed.
            if "meta" not in tables:
                raise ValueError
            values = dict(db.execute("SELECT key,value FROM meta"))
            config = json.loads(values.get("config", "null"))
            if not isinstance(config, dict) or (config.get("importer"), config.get("schema_version")) not in {
                ("animation-v1", 1), (IMPORTER, SCHEMA_VERSION),
            }:
                raise ValueError
            uuid.UUID(json.loads(values["campaign"]))
            required = {"position", "media_type", "tmdb_id", "status", "movie_pk", "wikidata_id",
                        "reason_code", "reason", "attempts", "partition_id", "source_page",
                        "dry_run_id", "dry_status", "dry_wikidata_id", "dry_reason_code", "dry_reason"}
            if not {"manifest", "partitions", "cache"} <= tables:
                raise ValueError
            if not {"key", "value"} <= {row[1] for row in db.execute("PRAGMA table_info(cache)")}:
                raise ValueError
            if not required <= {row[1] for row in db.execute("PRAGMA table_info(manifest)")}:
                raise ValueError
            partition_fields = {"id", "media_type", "mode", "lower_date", "upper_date", "page", "pages", "status", "limited"}
            if not partition_fields <= {row[1] for row in db.execute("PRAGMA table_info(partitions)")}:
                raise ValueError
            return config
    except (sqlite3.Error, ValueError, KeyError, TypeError):
        raise CommandError("State-dir is not a compatible import_animation campaign; use a separate directory.") from None


class AnimationState(State):
    def __init__(self, directory, config):
        previous = saved_config(directory)
        if previous is not None and {**previous, "importer": IMPORTER, "schema_version": SCHEMA_VERSION} != config:
            raise CommandError("State-dir belongs to another database or selection; use a separate directory.")
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.directory / "state.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            BEGIN;
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS manifest (
                position INTEGER PRIMARY KEY AUTOINCREMENT,
                media_type TEXT NOT NULL, tmdb_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', movie_pk INTEGER,
                partition_id INTEGER, source_page INTEGER NOT NULL DEFAULT 0,
                wikidata_id TEXT NOT NULL DEFAULT '', reason_code TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,
                dry_run_id TEXT NOT NULL DEFAULT '', dry_status TEXT NOT NULL DEFAULT '',
                dry_wikidata_id TEXT NOT NULL DEFAULT '',
                dry_reason_code TEXT NOT NULL DEFAULT '', dry_reason TEXT NOT NULL DEFAULT '',
                UNIQUE(media_type,tmdb_id)
            );
            CREATE INDEX IF NOT EXISTS animation_pending ON manifest(status,position);
            CREATE TABLE IF NOT EXISTS partitions (
                id INTEGER PRIMARY KEY, media_type TEXT NOT NULL, mode TEXT NOT NULL,
                lower_date TEXT NOT NULL DEFAULT '', upper_date TEXT NOT NULL DEFAULT '',
                page INTEGER NOT NULL DEFAULT 0, pages INTEGER,
                status TEXT NOT NULL DEFAULT 'pending', limited INTEGER NOT NULL DEFAULT 0,
                UNIQUE(media_type,mode,lower_date,upper_date)
            );
        """)
        if previous is None:
            self._meta("config", config)
            self._meta("campaign", str(uuid.uuid4()))
            for media in config["sources"]:
                self.db.execute("INSERT INTO partitions(media_type,mode) VALUES (?,'unfiltered')", (media,))
                self.db.execute("INSERT INTO partitions(media_type,mode,lower_date,upper_date) VALUES (?,'dated',?,?)",
                                (media, config["date_from"], config["date_to"]))
        elif previous.get("schema_version") == 1:
            # Same manifest layout: keep all IDs, results, cache and cursors.
            # No reading or reconstruction from the removed Django journal.
            self._meta("config", config)
        self.db.commit()
        self.campaign = self.meta("campaign")

    def _meta(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value)))

    def next_partition(self, media):
        return self.db.execute("SELECT * FROM partitions WHERE media_type=? AND status='pending' ORDER BY id LIMIT 1",
                               (media,)).fetchone()

    def save_pages(self, pages):
        """Store every ID AND all page/split cursors in a single durable commit."""
        with self.db:
            streams = [[(part["media_type"], row["id"], part["id"], part["page"] + 1)
                        for row in data["results"]] for part, data in pages]
            for group in zip_longest(*streams):
                for pair in group:
                    if pair:
                        self.db.execute("INSERT OR IGNORE INTO manifest(media_type,tmdb_id,partition_id,source_page) VALUES (?,?,?,?)", pair)
            for part, data in pages:
                page = part["page"] + 1
                total = data["total_pages"]
                overflow = total > MAX_PAGES or data.get("total_results", 0) > MAX_PAGES * 20
                if part["mode"] == "dated" and page == 1 and overflow and part["lower_date"] != part["upper_date"]:
                    start, stop = date.fromisoformat(part["lower_date"]), date.fromisoformat(part["upper_date"])
                    middle = start + (stop - start) // 2
                    for lower, upper in [(start, middle), (middle + timedelta(days=1), stop)]:
                        self.db.execute("INSERT OR IGNORE INTO partitions(media_type,mode,lower_date,upper_date) VALUES (?,'dated',?,?)",
                                        (part["media_type"], lower.isoformat(), upper.isoformat()))
                    self.db.execute("UPDATE partitions SET page=1,pages=?,status='split' WHERE id=?", (total, part["id"]))
                    continue
                # Freeze the size observed on the first page, never request 501.
                pages_count = part["pages"] if part["pages"] is not None else min(total, MAX_PAGES)
                done = page >= pages_count or not data["results"]
                self.db.execute("UPDATE partitions SET page=?,pages=?,status=?,limited=? WHERE id=?",
                                (page, pages_count, "done" if done else "pending",
                                 int(overflow or part["limited"]), part["id"]))

    def candidates(self, limit, dry_run_id=None, retry_skipped=False):
        statuses = "'pending','error','skipped'" if dry_run_id and retry_skipped else "'pending','error'"
        query = f"SELECT * FROM manifest WHERE status IN ({statuses})"
        parameters = []
        if dry_run_id:
            query += " AND dry_run_id!=?"
            parameters.append(dry_run_id)
        return self.db.execute(query + " ORDER BY position LIMIT ?", [*parameters, limit]).fetchall()

    def attempt(self, row):
        with self.db:
            self.db.execute("UPDATE manifest SET attempts=attempts+1 WHERE position=?", (row["position"],))

    def finish(self, row, status, *, movie_pk=None, qid="", code="", reason="", dry_run_id=None):
        with self.db:
            if dry_run_id:
                self.db.execute("UPDATE manifest SET dry_run_id=?,dry_status=?,dry_wikidata_id=?,dry_reason_code=?,dry_reason=? WHERE position=?",
                                (dry_run_id, status, qid, code, reason, row["position"]))
            else:
                self.db.execute("UPDATE manifest SET status=?,movie_pk=?,wikidata_id=?,reason_code=?,reason=? WHERE position=?",
                                (status, movie_pk, qid, code, reason, row["position"]))

    def created_count(self):
        return self.db.execute("SELECT COUNT(*) FROM manifest WHERE status='created'").fetchone()[0]

    def statistics(self, dry_run_id=None):
        candidates = dict(self.db.execute("SELECT status,COUNT(*) FROM manifest GROUP BY status").fetchall())
        result = {
            "failed_runs": self.meta("failed_runs", 0),
            "interrupted_runs": self.meta("interrupted_runs", 0),
            "candidates": candidates,
            "discovered": sum(candidates.values()),
            "processed": sum(value for key, value in candidates.items() if key not in {"pending", "error"}),
            "skips_by_reason": dict(self.db.execute("SELECT reason_code,COUNT(*) FROM manifest WHERE status='skipped' GROUP BY reason_code").fetchall()),
            "attempts": self.db.execute("SELECT COALESCE(SUM(attempts),0) FROM manifest").fetchone()[0],
            "coverage_limited_partitions": self.db.execute("SELECT COUNT(*) FROM partitions WHERE limited=1").fetchone()[0],
            "pending_partitions": self.db.execute("SELECT COUNT(*) FROM partitions WHERE status='pending'").fetchone()[0],
        }
        if dry_run_id:
            result["dry_run"] = dict(self.db.execute("SELECT dry_status,COUNT(*) FROM manifest WHERE dry_run_id=? GROUP BY dry_status",
                                                     (dry_run_id,)).fetchall())
            result["dry_skips_by_reason"] = dict(self.db.execute("SELECT dry_reason_code,COUNT(*) FROM manifest WHERE dry_run_id=? AND dry_status='skipped' GROUP BY dry_reason_code",
                                                                 (dry_run_id,)).fetchall())
        return result

    def report(self, summary=None):
        for filename, table, order in [("import_report.csv", "manifest", "position"), ("discovery_report.csv", "partitions", "id")]:
            cursor = self.db.execute(f"SELECT * FROM {table} ORDER BY {order}")
            temporary = self.directory / (filename + ".tmp")
            with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow([column[0] for column in cursor.description])
                writer.writerows(cursor)
            temporary.replace(self.directory / filename)
        if summary is not None:
            self.write_summary(summary)

    def write_summary(self, summary):
        temporary = self.directory / "summary.json.tmp"
        temporary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.directory / "summary.json")
