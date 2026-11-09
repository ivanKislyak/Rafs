# Backfill TMDB popularity

`backfill_tmdb_popularity` fills the existing `Movie.tmdb_popularity` and
corresponding **existing** movie search documents from one daily TMDB snapshot.
It does not import titles, edit identifiers/translations/relations, rebuild
vectors, replace document PKs, or change search ordering. Written with AI assistance.

The fields were introduced by migration
`0051_globalsearchindex_tmdb_popularity_and_more`. Apply outstanding migrations
through the usual deployment process before running this command. No new
migration is needed for the backfill.

## Input and identity

Supply both `movie_ids_MM_DD_YYYY.json.gz` and
`tv_series_ids_MM_DD_YYYY.json.gz` from the **same date**. The command validates
every JSONL record and the gzip streams, including their trailers, before any
Django writes. Missing/empty/corrupt files, duplicate IDs within a source,
invalid dates, and nonnumeric/negative/nonfinite popularity abort the run.
The files are streamed into temporary SQLite on disk, not loaded into RAM;
allow enough free space under the system temporary directory. Input files are
never changed.

Repeat `--import-state /path/to/state.sqlite3` for the manifests that populated
this database. Only confirmed real `created`, `updated`, and `existing` rows are
considered; pending/error/skipped/dry-only results are not evidence. The command
recognizes the original movie-only schema, the anime movie/TV schema, and
animation/series/country campaign schemas. SQLite states are opened read-only
and are never migrated or modified. Unknown/broken schemas abort before writes.

Each candidate is `(media_type, tmdb_id)`, so movie/10 and tv/10 are different.
`movie_pk` must be corroborated against the current Movie by cached Wikidata or
IMDb identity. A campaign's canonical Wikidata result can supplement its cached
details. A primary key, title, or year alone is never sufficient. Conflicting
identifiers, multiple media/ID pairs for one Movie, or a pair claimed by different
Movie PKs are retained for manual investigation. Redirect equivalence is not
guessed; contradictory canonical/external QIDs are reported as conflicts.
Missing detail-cache evidence is reported as `unverified_mapping`.

Without `--resolve-missing`, this is an offline operation and requires no API
credentials. Unmapped/unverified titles retain their previous value. All import
commands remain unchanged: their default popularity for newly imported titles
is still zero until a backfill supplies it.

### Optional exact Find fallback

`--resolve-missing` enables exact TMDB Find by valid IMDb and/or Wikidata IDs for
unmapped/unverified records, using the existing API client's sequential requests,
timeout, rate limits, Retry-After and retry handling. It requires
`TMDB_READ_TOKEN` or `TMDB_API_KEY` in the existing environment. Credentials are
not printed. It never searches by title/year or accepts episode/season results.
When both identifiers are available, both are checked; the combined movie/TV
result must be unambiguous and its external IDs must not contradict the Movie.
Local identity conflicts are not overridden by this fallback.

Only export popularity is used, not popularity from Find/details. An exactly
mapped ID absent from a validated export, or a successful Find confirming no
movie/TV match, yields `0.0`. An explicit export value of zero also counts as a
confirmed zero. These cases are reported separately. API failures, malformed
responses, 429/5xx/timeouts after retries, and identity conflicts preserve both
stored values. Lookup responses are cached in the temporary SQLite for this run;
they are not persisted between invocations. Large fallback runs can therefore
make many requests; preview their coverage and cost before applying.

TMDB references:
[daily exports](https://developer.themoviedb.org/docs/daily-id-exports),
[Find by external ID](https://developer.themoviedb.org/reference/find-by-id).

## Commands on the server

Use the same downloaded files for the preview, dry-run and apply. For example,
download the November 8 snapshot into a new directory:

```bash
cd ~/apps/Rafs
source .venv/bin/activate
mkdir -p .rafs_import/popularity-exports
curl --fail --location --output .rafs_import/popularity-exports/movie_ids_11_08_2026.json.gz \
  https://files.tmdb.org/p/exports/movie_ids_11_08_2026.json.gz
curl --fail --location --output .rafs_import/popularity-exports/tv_series_ids_11_08_2026.json.gz \
  https://files.tmdb.org/p/exports/tv_series_ids_11_08_2026.json.gz
```

The date is an example: choose an available, completed daily snapshot and use
its date in both filenames. TMDB retains daily exports for a limited period.
Do not run while an importer is writing; PostgreSQL uses the existing shared
`database_lock()` and rejects a competing writer instead of waiting in a queue.

Build reusable **Bash** arguments. Include only state paths that actually exist
and belong to the target database; append custom state directories as needed:

```bash
args=(
  --movie-export .rafs_import/popularity-exports/movie_ids_11_08_2026.json.gz
  --tv-export .rafs_import/popularity-exports/tv_series_ids_11_08_2026.json.gz
)
for state in \
  .rafs_import/state.sqlite3 \
  .rafs_import/anime/state.sqlite3 \
  .rafs_import/animation/state.sqlite3 \
  .rafs_import/series/state.sqlite3 \
  .rafs_import/country_movies/RU-UA-KZ/state.sqlite3
do
  if [ -f "$state" ]; then args+=(--import-state "$state"); fi
done
```

Preview the first 100 titles, then optionally apply those 100:

```bash
python -u manage.py backfill_tmdb_popularity "${args[@]}" --limit 100 --dry-run
python -u manage.py backfill_tmdb_popularity "${args[@]}" --limit 100
```

Full dry-run and full apply are separate commands:

```bash
python -u manage.py backfill_tmdb_popularity "${args[@]}" --dry-run
python -u manage.py backfill_tmdb_popularity "${args[@]}" --batch-size 500
```

To resolve remaining mappings, explicitly add `--resolve-missing` to both a
preview and its apply. Review conflicts instead of attempting to force them.
No mass apply is performed by tests or automatically on application startup.

## Batches, reporting and resume

Movies are scanned in ascending PK order. `--limit` limits **scanned** titles,
including unresolved ones; zero means no limit. `--after-pk N` starts strictly
after N. `--batch-size` defaults to 500. Files/states are fully prepared again
on each invocation, even for a bounded run.

HTTP and mapping lookup finish before each short Django transaction. Movie and
search popularity changes commit together, only when values differ. Search
documents are checked even when Movie already has the desired value. Missing
documents are counted for **all scanned Movies**, including unresolved ones;
the command does not create documents. If identifiers change between lookup and
the transaction, that record is retained and reported separately.

Each committed batch prints `last_pk` and cumulative counters. The final summary
includes viewed/updated Movies, updated documents, confirmed zeros (and their
sources), conflicts, source errors, missing/unverified mappings, unprocessed
records, concurrent identity changes, and missing search documents. Source
errors are also split into HTTP 429, HTTP 5xx, network timeout/connection failure,
access denial, invalid response, and other API errors. The shared client reports
timeouts and connection failures together. Dry-run
uses the same counters as **would update**, writes no Django data, and takes no
writer lock. Its checkpoint is labeled `DRY RUN`, not committed progress.

If a write fails, the whole current batch rolls back; earlier batches remain.
Use the last printed committed `last_pk` with the **same inputs** to continue:

```bash
python -u manage.py backfill_tmdb_popularity "${args[@]}" --after-pk 12345
```

Replace 12345 with your checkpoint. That checkpoint includes unresolved rows
that were intentionally retained. After fixing sources or enabling fallback,
rerun from the beginning to revisit them; an unchanged input run is idempotent.
A lost terminal/checkpoint or process kill can also be handled by rerunning
from the beginning: updates only touch changed popularity values.

This backfill and `rebuild_search_index` must be scheduled separately. The
backfill never calls an importer, `refresh_movie_documents`, or a rebuild.
Missing documents may be rebuilt in a separate maintenance step if desired:

```bash
python manage.py rebuild_search_index
```

The normal movie document builder now copies popularity from Movie, so a later
rebuild preserves it. A rebuild can replace document PKs/vectors according to
its own existing behavior; that is not part of this backfill.
