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

- Home page with administrator-curated, translated collections above the
  existing top movies ranked by review activity and average user score
- Collection carousels with native horizontal scrolling, scroll snap, optional
  previous/next controls, and keyboard/touch access; all prepared items remain
  available, with roughly five visible on wide screens and no collection ratings
- Responsive movie catalog with poster cards and incremental loading
- Individual movie pages with ratings, reviews, and watch-status controls
- Reviews feed with incremental loading and links to authors and reviewed works
- User registration, login, and secure POST-based logout
- Custom users with avatars, levels, and Frames — the RAFS experience points
- Public profiles at `/@<username>/` with review/reply counts, achievements,
  and a library grouped by watch status; email and owner controls are private
- Owner-only settings at `/settings/` for display name, username, biography,
  sex, date of birth, and avatar, with inline validation and a shared save action
- Square avatar cropping with drag, zoom, touch, and keyboard controls;
  previewed upload/removal takes effect only after **Save changes**
- Separate email changes protected by the current password
- Removal from the owner's watch library with confirmation, updated counts,
  and an undo action
- Existing achievement badges with image fallbacks, administrator-controlled
  profile visibility, and user awards stored through `UserAchievement`
- Automatic "Review or Treat" achievement awards for qualifying written reviews,
  with a server-issued notification and Halloween badge-reveal dialog
- Movie ratings based on an overall score and optional additional criteria
- Creation, editing, and deletion of user reviews
- Expandable review-reply threads, posting replies, and deletion of reviews or
  replies by their author or a superuser
- Inline reply editing by the reply's author on movie pages and the reviews feed,
  including incrementally loaded content, without a full-page reload
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
- Broad whole-series imports and production-country movie imports for RU, UA,
  and KZ, including co-productions, with independent resumable campaign state
- Automatic poster-URL import and missing-cover backfill through the TMDB importer
- Local movie-cover uploads, remote cover URLs, and placeholder fallbacks
- PostgreSQL connection settings for development and production deployments,
  selected through environment variables
- User-interface localization with English, Russian, Ukrainian, Kazakh, Spanish, and German language switching
- Shared header and footer templates with component-based CSS
- Light/dark themes, a compact mobile header, and public community guidelines
- Reversible Halloween 2026 styling with neutral surfaces, pumpkin-orange actions,
  purple artwork, restrained green details, and seasonal favicons
- Canonical URLs, localized page descriptions, Open Graph metadata,
  homepage WebSite structured data, `sitemap.xml`, and `robots.txt`

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
- Django REST Framework for search, search history, current-user profile,
  watch-status, and review-reply APIs
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
  whenever the searchable data changes, as described below. The animation,
  series, and country-movie campaign commands are exceptions: they refresh
  their affected Movie documents.
- **Search suggestions are not live catalog autocomplete.** They show the signed-in
  user's history, or popular-query data when supplied to the template.
- **Account settings have limits.** Changing a username changes the public
  profile URL; the old address is not retained as a redirect. Email changes
  require the current password but do not verify ownership of the new address
  by email. Settings require JavaScript, and there is no date-of-birth check
  rejecting future dates.
- **Seasonal awards require event configuration.** "Review or Treat" awarding and
  presentation are implemented, but require an achievement definition with code
  `review-or-treat-2026` and valid timezone-aware event dates. Missing or invalid
  configuration skips the award without blocking review submission. A Frames
  notification alone is not an achievement signal.
- **Reply tools are basic.** Authors can post and edit their own replies;
  authors and superusers can delete them. Reply reactions and a broader moderation
  workflow are not exposed by the current interface.
- **Homepage collections need administrator setup.** Only published, non-empty
  collections appear; no demo collections or movie selections are created by the
  seasonal theme.
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

## Homepage collections

Collections are managed through `HomepageCollection` in Django admin:

1. Add a collection, provide its translated title, and set its `position`.
2. Add existing movies through the inline collection items and set their positions.
3. Enable `is_published` when the collection is ready to appear on the home page.

Collections and their items are ordered by `position`, then primary key. Empty or
unpublished collections are omitted. Titles use the project's language fallback
conventions, and each movie retains its detail link, poster fallback, title, and
year when available. The number of visible cards is a layout choice, not a limit
on the collection's contents. There is no autoplay or carousel dependency; the
native scroll area and movie links remain usable without JavaScript.

The home view supplies `homepage_collections` separately from `top_movies`.
Templates access `collection.items.all` and `item.movie`. Collection cards pass
`hide_rating=True` to `movies/_movie_card.html`: the entire rating branch is
skipped, including access to `movie.avg_rating`. Catalog cards, top movies, and
other callers retain their existing rating display.

## Themes and Halloween 2026

The ordinary light/dark theme switch still stores its choice under `rafs-theme`
in localStorage. The seasonal appearance is a separate, frontend-only switch in
[`templates/base.html`](templates/base.html):

```html
<html lang="{{ CURRENT_LANGUAGE }}">
```

- **Enable Halloween:** add `data-event="halloween-2026"` to the root `<html>` tag.
- **Disable Halloween:** remove that attribute and reload the page. The ordinary
  palette, header/footer artwork, favicon, and logo hover behavior return.

The attribute is currently absent: the ordinary red appearance is restored after
Halloween 2026. The seasonal switch is not controlled by a
date, backend setting, API, or administrator publication flag. Disabling the
seasonal appearance does not hide published homepage collections.

[`static/css/halloween.css`](static/css/halloween.css) loads after page-specific
styles and scopes seasonal overrides to `html[data-event="halloween-2026"]`.
Dark mode uses neutral charcoal surfaces and warm-white text; light mode uses
neutral light surfaces and darker accent text. Pumpkin orange marks primary
actions, active navigation, selected controls, and the small RAFS page eyebrow.
Orange buttons use dark text. Purple remains in the supplied artwork and
supporting accents; muted green is limited to small decorative details. Error
and destructive states remain distinct.

Original assets are preserved. Seasonal artwork lives in
[`static/images/halloween/`](static/images/halloween/):

- `halloween_def_rafs_logo.png`: primary header logo.
- `halloween_darkpurple_gl_rafs_logo_for_leftside.png`: purple hover layer,
  moving **left**.
- `halloween_darkgreen_gl_rafs_logo_for_rightside.png`: green hover layer,
  moving **right**.
- `halloween_glitched_rafs_logo.png`: coordinated hover alternate.
- `halloween_footer_logo.png`: footer artwork.
- `halloween_favicon.ico` and `halloween_favicon.png`: seasonal favicon links,
  synchronized with the root attribute by `static/js/event-assets.js`.

Logo motion is limited to hover-capable pointing devices and respects
`prefers-reduced-motion`. The seasonal switch also controls the Halloween
award-reveal dialog; it does not enable or disable server-side awarding. When
the theme is off, an earned achievement uses the ordinary notification instead.
See [Review or Treat](#review-or-treat) for the presentation and eligibility rules.

## Profiles and achievements

Public profiles use `/@<username>/`. The heading displays the user's `name`,
falling back to `username` when no display name is set. Biography text is public;
email, sex, and date of birth are not exposed on another user's profile.

All profile-editing controls are on the signed-in user's `/settings/` page,
linked from their profile. It contains avatar controls, display name, username
with a visible `@` prefix, biography, private sex/date-of-birth fields, and a
separate email editor. The `@` prefix is not part of the saved username.

**Save changes** submits changed profile fields and any prepared avatar together
using a multipart PATCH request. Validation errors leave the saved profile
unchanged and preserve the entered values and avatar preview for correction.
An unsaved-changes hint clears after saving or restoring the saved values;
leaving the page does not trigger a browser warning.

Choosing an avatar opens a square crop dialog with dragging, zoom, touch, and
arrow-key controls. Confirming prepares a 512 × 512 PNG preview; canceling keeps
the previous preview, including any earlier draft. Removal requires confirmation
and also waits for **Save changes**. **Undo** restores the saved avatar.
Uploaded images are validated on the server, limited to 12 MB, and converted to
PNG. The older avatar POST endpoint remains available for existing callers.

Changing email is an independent action requiring the current password. The new
address is applied immediately; no confirmation email is sent. Changing a
username keeps the user on `/settings/` and updates their profile links in the
header. Their new public address resolves to the same account; the old address
returns 404 while unassigned.

The authenticated APIs always select `request.user`:

| Endpoint | Purpose |
| --- | --- |
| `/accounts/api/v1/me/settings/` | GET/PATCH for combined profile fields and staged avatar upload/removal |
| `/accounts/api/v1/me/email/` | GET/PATCH for email; updates require `current_password` |
| `/accounts/api/v1/me/username/` | GET/PATCH for username and the resulting `profile_url` |
| `/accounts/api/v1/me/` | Existing profile API for `name`, `about`, `sex`, and `bd_date`; `id` and `username` remain read-only |

Settings requests use session authentication and CSRF protection. A supplied
user ID cannot select another account for editing.

Reply authors can edit reply text through the inline editor, backed by
`PATCH /movies/api/v1/replies/<reply_id>/`. Superuser deletion privileges do not
grant permission to edit another user's reply.

`User.achievement` uses `UserAchievement` as its through model, with a unique
user/achievement pair, an `earned_at` field, and an optional `source_review`.
Achievement definitions include `badge_image`, `code`, event dates, and
`display_in_profile`. Both definitions and award records are available in admin.

The profile receives only achievements with `display_in_profile=True`; its count
and list use the same prefetched data, including `badge_image`. Existing badges
show their image with a diamond fallback. An empty award list remains empty,
and award timestamps are not currently displayed.

### Review or Treat

[`accounts/services/achievements.py`](accounts/services/achievements.py) implements
automatic awarding when a valid saved review first acquires non-whitespace text:

- A new written review qualifies, as does adding text to an existing numeric-only
  rating. There is no Halloween-movie restriction or additional minimum text length.
- A numeric rating with empty/whitespace-only text does not qualify. Editing or
  resaving a review that already had non-whitespace text does not qualify.
- The server checks `starts_at <= now < ends_at` on the achievement definition
  with code `review-or-treat-2026`. Event dates are configuration, not browser rules.
- `get_or_create` and the unique user/achievement constraint make the award
  one-time per user. The record stores the server's award time and source review;
  another qualifying review does not replace them or send a second award message.

To configure the October 31–November 3, 2026 event inclusive in UTC+5, create the
achievement in admin with its name, description, optional `badge_image`, and code
`review-or-treat-2026`. Use timezone-aware bounds equivalent to
`2026-10-31T00:00:00+05:00` through `2026-11-04T00:00:00+05:00` (exclusive end).
`display_in_profile` controls profile visibility and its count, not eligibility.
The code does not automatically create the event definition or its artwork.

Review saving and awarding run in one database transaction. Only a newly created
award schedules the Django message with tags
`halloween-award-earned review-or-treat-2026`, after commit. The inclusion tag in
[`accounts/templatetags/achievements.py`](accounts/templatetags/achievements.py)
also checks that the signed-in user owns the persisted award before supplying
presentation data. Ordinary review success and `frames-reward` messages do not
trigger the achievement presentation or grant an award.

With the Halloween appearance active, JavaScript, and dialog support,
[`static/js/halloween-award.js`](static/js/halloween-award.js) displays
`jigsaw_boo.jpg`, followed by the earned badge when the user selects **Skip to
award** or presses Escape. There is no sound or timer advancing the scare.
With `prefers-reduced-motion: reduce`, the scare is skipped and the badge appears
directly. Images load only when their presentation stage is shown; an unavailable
scare image also advances to the badge. The dialog has a profile link and close
control, keeps keyboard focus inside, and restores focus/scroll on closing.

The achievement presentation is queued before ordinary messages, preserving the
separate Frames notification. Without the seasonal dialog, the normal award
notification remains available; notifications are also readable without
JavaScript. Closing or skipping the presentation does not create, revoke, or
re-award the achievement.

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
- Profile settings: <http://127.0.0.1:8000/settings/> (sign-in required)
- About RAFS: <http://127.0.0.1:8000/about_site/>
- Community guidelines: <http://127.0.0.1:8000/community-guidelines/>
- Sitemap: <http://127.0.0.1:8000/sitemap.xml>
- Robots rules: <http://127.0.0.1:8000/robots.txt>
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

`import_series` expands the campaign runner to whole TV/mini-series across
countries, genres, and platforms, including animation and anime. It does not
import individual seasons or episodes. `import_country_movies` selects movies
produced in any of RU, UA, or KZ by default (`--countries` can select a subset).
Selection is checked against TMDB `production_countries`, not inferred from the
original language; co-productions qualify, while contradictory country data is
skipped for review.

Both new commands require PostgreSQL. They use separate state/cache/report
directories and default to `--target-new 0`, scanning available partitions without
the animation campaign's 15,000-card target. An optional positive target can exceed
15,000; `--max-candidates` bounds a single invocation. Neither command guarantees
complete source coverage. Like the animation importer, they preserve existing
non-empty fields and refresh affected Movie search documents after writes.

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
The [series importer guide](movies/management/commands/README_import_series.md)
and [country-movie importer guide](movies/management/commands/README_import_country_movies.md)
cover the new selections, bounded dry-runs, independent campaign state, and
resume/coverage limits. Campaign imports share a writer lock and should be run
sequentially; a competing writer is rejected rather than queued.

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

The repository includes automated checks for profile privacy, owner-only
settings, display-name/username changes, password-protected email changes,
combined profile/avatar validation and rollback, avatar uploads, localized watch
libraries, search-history validation and
ownership, review reactions, reply creation/editing permissions, watch statuses,
home-page rankings, SEO metadata, POST-only staff imports, and importer behavior
using API fixtures. Achievement tests cover eligibility, event boundaries,
idempotency, transaction rollback, owned-award presentation data, and concurrent
awards; the concurrency check requires PostgreSQL. Series/country-movie importer
tests cover selection, identity conflicts, dry-runs, state isolation, and resume.
The full-text rebuild checks require a separate PostgreSQL test database; the
database role must be allowed to create that test database. Run the test suite with:

```powershell
python manage.py test
```

For the account settings checks alone, run:

```powershell
python manage.py test accounts
```

The account suite uses temporary media storage for uploads. Its server-side
tests do not replace browser checks of avatar dragging, touch gestures, dialog
cancellation, and unsaved form state.

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

- Email-address verification for email changes
- Reply reactions and expanded moderation tools
- Expanded Wikidata synchronization
- Incremental search-index maintenance, refresh automation, and catalog autocomplete
- Personalized movie recommendations
- Production-ready container startup and deployment configuration
- Dedicated production media-file storage
- Expanded PostgreSQL-search and browser-interaction test coverage

## Project structure

- `accounts/` — authentication, custom users, profile editing, achievement
  definitions/award records, and search history
- `accounts/services/achievements.py` — server-side seasonal eligibility and awards
- `accounts/templatetags/achievements.py` — owned-award data for presentation
- `movies/` — catalog works, ratings, reviews, replies, votes, and watch statuses
- `movies/services/` — Wikidata requests/imports, shared catalog campaign runners,
  and PostgreSQL search-index helpers
- `movies/management/commands/` — catalog imports, translations, and importer guides
- `core/` — home page, translated homepage collections, general site pages,
  SEO helpers, and sitemaps
- `templates/` — shared Django templates, including the header and footer
- `static/css/components/` — shared interface-component styles
- `static/css/halloween.css` — scoped seasonal palette and component overrides
- `static/js/home-collections.js` — optional collection navigation controls
- `static/js/event-assets.js` — seasonal favicon switching
- `static/js/halloween-award.js` — server-signalled scare/badge presentation
- `static/images/halloween/` — seasonal artwork and reward-presentation assets
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
