# RAFS

<p align="center">
  <img src="static/images/rafs-preview-v3.png" alt="RAFS wasp mascot" width="760">
</p>

RAFS is a Django web application for discovering, rating, and discussing films,
series, and anime.

The project is currently in active development and is being built as an educational portfolio project.

## Live demo

RAFS is available at [https://rafs.app](https://rafs.app/).

The public version is actively updated and may contain unfinished
interfaces or temporary development data.

## Current features

- Home page with movies ranked by review activity and average user score
- Responsive movie catalog with poster cards and incremental loading
- Individual movie pages with ratings, reviews, and watch-status controls
- Reviews feed with incremental loading and links to authors and reviewed works
- User registration, login, and secure POST-based logout
- Custom users with avatars, levels, and Frames — the RAFS experience points
- Public profiles at `/@<username>/` with review/reply counts, achievements,
  and a library grouped by watch status; email and owner controls are private
- Avatar upload, resizing, conversion to PNG, and removal from the owner's profile
- Movie ratings based on an overall score and optional additional criteria
- Creation, editing, and deletion of user reviews
- Expandable review-reply threads, posting replies, and deletion of reviews or
  replies by their author or a superuser
- Spoiler warnings for written reviews
- Optimistic like/dislike updates on reviews, synchronized with the server and
  rolled back on error, without reloading the page
- Personal movie watch statuses updated through the Fetch API
- A 100-Frame reward and animated notification for the first review of a movie
- Average movie ratings calculated from user reviews
- PostgreSQL-backed global search from the header using a separate search index
- Authenticated users' recent search history in header suggestions, with query
  reuse and individual history-entry deletion
- Staff-only movie search and metadata import from Wikidata
- TMDB/Wikidata command-line imports for popular movies and anime films/series,
  with dry-run, caching, saved progress, and resume support
- Automatic poster-URL import and missing-cover backfill through the TMDB importer
- Local movie-cover uploads, remote cover URLs, and placeholder fallbacks
- PostgreSQL connection settings for development and production deployments,
  selected through environment variables
- User-interface localization with English, Russian, Ukrainian, Kazakh, Spanish, and German language switching
- Shared header and footer templates with component-based CSS
- Light/dark themes, a compact mobile header, and public community guidelines

These features depend on local data, database selection, and optional API
credentials. See [Current limitations](#current-limitations) before a first run.

## Technologies

- Python 3.11+
- Django 5.2.16
- SQLite for lightweight local development
- PostgreSQL for full-text search and production database connections;
  PostgreSQL 17 is included in the development Docker setup
- Docker and Docker Compose
- Django ORM and Django Template Language
- Django REST Framework for the authenticated search-history API
- HTML and component-based CSS
- Vanilla JavaScript and the Fetch API
- django-parler for translated movie metadata
- django-taggit for movie tags
- Requests for TMDB and Wikidata integration
- Pillow for image handling
- python-dotenv for environment variables
- WhiteNoise for static-file delivery

The complete list of Python dependencies is available in `requirements.txt`.

## Current limitations

- **A fresh clone has no catalog or user activity.** Movies, covers, users,
  reviews, and ratings from the live site are not bundled. The home page ranks
  reviewed works, so adding catalog records alone does not populate its top list.
- **Global header search requires PostgreSQL and a populated search index.**
  SQLite is useful for lightweight local development but does not support the
  PostgreSQL full-text query used by the search-results page. Importing or editing
  records does not automatically update `GlobalSearchIndex`. Run
  `python manage.py rebuild_search_index` after the initial data setup and again
  whenever the searchable data changes, as described below. The animation
  campaign command is an exception: it refreshes its affected Movie documents.
- **Search suggestions are not live catalog autocomplete.** They show the signed-in
  user's history, or popular-query data when supplied to the template.
- **Profile editing is partial.** Public profiles and avatar management work;
  a general editor for username, biography, and other account fields is not yet
  available. Achievement display exists, but automatic achievement awards are
  not implemented.
- **Reply tools are basic.** Replies can be posted, shown/hidden, and deleted with
  ownership/superuser checks. Reply reactions, reply editing, and a broader
  moderation workflow are not exposed by the current interface.
- **Catalog filtering has no separate form.** The view accepts `query`,
  `min_rating`, `year_from`, and `year_to` parameters; the visible search is in
  the shared header.
- **Import and poster coverage depend on external data.** TMDB credentials and
  explicit command execution are needed for automatic poster acquisition.
  Missing or ambiguous IDs, unavailable translations/posters, rate limits, and
  Wikidata maxlag can leave records incomplete or skipped. Anime selection is
  conservative rather than exhaustive, and individual episodes are not imported.
- **PostgreSQL support is not a complete production deployment.** The included
  containers use Django's development server. Production application serving,
  media-file delivery, and database operations must be configured separately.

## Running with Docker

The included Docker configuration is intended for development. It runs the
Django development server together with PostgreSQL 17 and mounts the project
directory into the web container, so source-code changes are available without
rebuilding the image.

This setup provides PostgreSQL for the global search implementation. A fresh
database still needs catalog data and search-index population as described above.

Clone the repository and create the environment file:

```powershell
git clone https://github.com/ivanKislyak/Rafs.git
cd Rafs
Copy-Item .env.example .env
```

Before starting the containers, replace the placeholder values in `.env`,
especially `SECRET_KEY` and `DB_PASSWORD`. Docker Compose overrides
`DB_ENGINE`, `DB_HOST`, and `DB_PORT` for the web container, so it connects to
the included PostgreSQL service automatically.

Build the image, apply the migrations, and start the project:

```powershell
docker compose build
docker compose run --rm web python manage.py migrate
docker compose up
```

RAFS will be available at <http://127.0.0.1:8000/>. PostgreSQL is also exposed
to the host at `127.0.0.1:5433` for optional use with a database client.

Create an administrator while the containers are running:

```powershell
docker compose exec web python manage.py createsuperuser
```

Stop the containers with `Ctrl+C` followed by:

```powershell
docker compose down
```

The `postgres_data` volume preserves the Docker database between restarts.
Running `docker compose down -v` also removes that volume and permanently
deletes its database contents.

## Running locally without Docker

Clone the repository:

```powershell
git clone https://github.com/ivanKislyak/Rafs.git
cd Rafs
```

Create and activate a virtual environment on Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install all dependencies:

```powershell
python -m pip install -r requirements.txt
```

Create a local environment file from the example:

```powershell
Copy-Item .env.example .env
```

At minimum, the local `.env` file should contain:

```dotenv
SECRET_KEY=your-local-secret-key
DJANGO_DEBUG=True
```

The default `DB_ENGINE=sqlite` setting uses the local `db.sqlite3` file and
ignores the PostgreSQL connection variables. To connect directly to the Docker
PostgreSQL service from the host instead, use `DB_ENGINE=postgres`,
`DB_HOST=127.0.0.1`, and `DB_PORT=5433` while the database container is running.
The SQLite setup does not support non-empty global full-text searches; use
PostgreSQL when working on that feature.

Apply the migrations and start the development server:

```powershell
python manage.py migrate
python manage.py runserver
```

The following pages will then be available:

- Home page: <http://127.0.0.1:8000/>
- Movie catalog: <http://127.0.0.1:8000/movies/>
- Reviews page: <http://127.0.0.1:8000/movies/reviews/>
- Public profile: `/@<username>/` after registering a user
- Community guidelines: <http://127.0.0.1:8000/community-guidelines/>
- Staff Wikidata search: <http://127.0.0.1:8000/movies/wikidata/search/>
- Django admin: <http://127.0.0.1:8000/admin/>

## Local data and movie covers

The local `db.sqlite3` database and the entire `media/` directory are excluded
by `.gitignore`. A fresh clone therefore does not include the movies, users,
ratings, or reviews from the development database.

When Docker is used, PostgreSQL data is stored in the named `postgres_data`
volume. The project directory is mounted at `/app`, so uploaded media files are
still written to the host-side `media/` directory and remain excluded from Git.

### Adding catalog records and covers manually

Create an administrator account:

```powershell
python manage.py createsuperuser
```

Movie records can be created through [Django admin](http://127.0.0.1:8000/admin/)
or imported from Wikidata through the staff-only page:

<http://127.0.0.1:8000/movies/wikidata/search/>

The staff Wikidata page imports metadata and related entities; it does not fetch
posters. For a manual cover, edit the movie's `cover` field in Django admin or
provide a remote `cover_url`.

### Importing catalog records and poster URLs automatically

`import_popular_movies` uses TMDB discovery, translations, and poster URLs with
Wikidata identity checks and relations. It also searches for missing covers on
existing records with suitable IDs. `import_anime` supports TMDB movie and TV
sources for anime films and whole series, with a separate saved state.
`import_animation` covers all Animation movie/TV works (including anime by
default), with resumable date partitions and a practical target of up to 15,000
new cards. It requires PostgreSQL and stores progress/cache in SQLite; a crash
after the Movie commit may undercount new cards, while ID checks prevent duplicates.

Add your TMDB API Read Access Token to the local `.env` file:

```dotenv
TMDB_READ_TOKEN=your-tmdb-read-token
```

Alternatively, the importers accept `TMDB_API_KEY`. Preview 20 movie candidates
and at most 20 existing records needing cover backfill without changing Django
data, then run the same small import:

```powershell
python manage.py import_popular_movies --limit 20 --backfill-limit 20 --dry-run
python manage.py import_popular_movies --limit 20 --backfill-limit 20
```

Dry-run still contacts the APIs and writes its separate cache, candidate list,
and reports under `.rafs_import/`. Repeating a command resumes saved progress.
These imports are operator-run commands, not a background task started by the
website. See the [popular-movie importer guide](movies/management/commands/README_import_popular_movies.md)
and [anime importer guide](movies/management/commands/README_import_anime.md)
for filters, identity checks, missing-cover-only runs, and retry/resume options.
The [animation campaign guide](movies/management/commands/README_import_animation.md)
documents the 40-candidate dry-run, tmux operation, accounting and coverage limits.

Posters are stored as remote URLs, not downloaded into `media/`, and existing
local covers and non-empty cover URLs are preserved by these command-line
importers. Posters and complete translations are not available for every work.

A movie can use either an uploaded image from its `cover` field or a
remote URL stored in `cover_url`. The interface displays a default
placeholder when neither source is available or an image cannot be
loaded.

With `DJANGO_DEBUG=True`, Django serves media files during local development. Media storage and delivery must be configured separately for a production deployment. WhiteNoise serves static assets, not user-uploaded media files.

## Building and rebuilding the search index

Global search requires PostgreSQL. After applying migrations and adding the
initial data, build the index with:

```powershell
python manage.py rebuild_search_index
```

Use the same command after importing, editing, or deleting searchable records.
Index updates are manual: changing data does not automatically refresh search.
For a running Docker environment, use:

```powershell
docker compose exec web python manage.py rebuild_search_index
```

The command replaces only `GlobalSearchIndex`, using the existing document
builders for movies, non-empty reviews by active users, active users, persons,
and studios. Deleted users and their reviews are excluded. It refreshes changed
documents and removes stale entries without modifying the source records or
calling external APIs. The rebuild runs in one transaction: an error preserves
the previous index. SQLite is not supported by this command.

## Project checks

Check the Django configuration:

```powershell
python manage.py check
```

The repository includes automated checks for profiles, avatar uploads, search
history validation and ownership, review reactions and replies, watch statuses,
SEO metadata, POST-only staff imports, and importer behavior using API fixtures.
The full-text rebuild checks require a separate PostgreSQL test database; the
database role must be allowed to create that test database. Run the test suite with:

```powershell
python manage.py test
```

For a running Docker environment, the same checks can be executed inside the
web container:

```powershell
docker compose exec web python manage.py check
docker compose exec web python manage.py test
```

Collect static files for deployment:

```powershell
python manage.py collectstatic --noinput
```

## Planned features

- General profile editing beyond avatar management
- Reply reactions, reply editing, and expanded moderation tools
- Expanded Wikidata synchronization
- Search-index maintenance commands, refresh automation, and catalog autocomplete
- Personalized movie recommendations
- Automatic achievement awards
- Production-ready container startup and deployment configuration
- Dedicated production media-file storage
- Expanded PostgreSQL-search and browser-interaction test coverage

## Project structure

- `accounts/` — authentication, custom users, profiles, achievements, and search history
- `movies/` — catalog works, ratings, reviews, replies, votes, and watch statuses
- `movies/services/` — Wikidata requests/imports and PostgreSQL search-index helpers
- `movies/management/commands/` — catalog imports, translations, and importer guides
- `core/` — home page and general site pages
- `templates/` — shared Django templates, including the header and footer
- `static/css/components/` — shared interface-component styles
- `static/` — JavaScript, fonts, logos, and other interface assets
- `locale/` — gettext translations for the supported interface languages
- `media/` — user-uploaded files excluded from the repository
- `config/` — settings and root URL configuration
- `Dockerfile` and `compose.yaml` — development containers for Django and PostgreSQL

## License

The source code is available under the PolyForm Noncommercial
License 1.0.0.

Running a paid or advertising-supported derivative service requires
prior written permission.

The RAFS name, logo, and wasp mascot are not included in the software
license. See `BRAND_ASSETS.md`.

Movie posters, fonts, and other third-party materials remain the
property of their respective owners.
