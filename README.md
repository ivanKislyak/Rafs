# RAFS

<p align="center">
  <img src="static/images/rafs-preview-v3.png" alt="RAFS wasp mascot" width="760">
</p>

RAFS is a Django web application for discovering, rating, and discussing movies.

The project is currently in active development and is being built as an educational portfolio project.

## Live demo

RAFS is available at [https://rafs.app](https://rafs.app/).

The public version is actively updated and may contain unfinished
interfaces or temporary development data.

## Current features

- Home page with movies ranked by review activity and average user score
- Movie catalog with title search and rating/year filters
- Individual movie pages with ratings, reviews, and watch-status controls
- User registration, login, and secure POST-based logout
- Custom users with avatars, levels, and Frames — the RAFS experience points
- Movie ratings based on an overall score and optional additional criteria
- Creation, editing, and deletion of user reviews
- Spoiler warnings for written reviews
- Like and dislike reactions updated asynchronously without reloading the page
- Personal movie watch statuses updated through the Fetch API
- A 100-Frame reward and animated notification for the first review of a movie
- Average movie ratings calculated from user reviews
- Staff-only movie search and metadata import from Wikidata
- Local movie-cover uploads, remote cover URLs, and placeholder fallbacks
- User-interface localization with English, Russian, Ukrainian, Kazakh, Spanish, and German language switching
- Shared header and footer templates with component-based CSS

## Technologies

- Python 3.11+
- Django 5.2.16
- SQLite for lightweight local development
- PostgreSQL 17 for Docker-based development
- Docker and Docker Compose
- Django ORM and Django Template Language
- HTML and component-based CSS
- Vanilla JavaScript and the Fetch API
- django-parler for translated movie metadata
- django-taggit for movie tags
- Requests for Wikidata integration
- Pillow for image handling
- python-dotenv for environment variables
- WhiteNoise for static-file delivery

The complete list of Python dependencies is available in `requirements.txt`.

## Running with Docker

The included Docker configuration is intended for development. It runs the
Django development server together with PostgreSQL 17 and mounts the project
directory into the web container, so source-code changes are available without
rebuilding the image.

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

Apply the migrations and start the development server:

```powershell
python manage.py migrate
python manage.py runserver
```

The following pages will then be available:

- Home page: <http://127.0.0.1:8000/>
- Movie catalog: <http://127.0.0.1:8000/movies/>
- Reviews page: <http://127.0.0.1:8000/movies/reviews/>
- Staff Wikidata search: <http://127.0.0.1:8000/movies/wikidata/search/>
- Django admin: <http://127.0.0.1:8000/admin/>

## Local data and movie covers

The local `db.sqlite3` database and the entire `media/` directory are excluded
by `.gitignore`. A fresh clone therefore does not include the movies, users,
ratings, or reviews from the development database.

When Docker is used, PostgreSQL data is stored in the named `postgres_data`
volume. The project directory is mounted at `/app`, so uploaded media files are
still written to the host-side `media/` directory and remain excluded from Git.

Movie covers are not currently distributed with the repository either. They must be uploaded manually:

1. Create an administrator account:

   ```powershell
   python manage.py createsuperuser
   ```

Movie records can be created manually through Django admin or imported
from Wikidata through the staff-only page:

<http://127.0.0.1:8000/movies/wikidata/search/>

The Wikidata importer currently retrieves movie metadata and related
entities. Poster acquisition is still handled separately.

2. Open <http://127.0.0.1:8000/admin/>.
3. Create or edit a movie and upload an image through its `cover` field.

A movie can use either an uploaded image from its `cover` field or a
remote URL stored in `cover_url`. The interface displays a default
placeholder when neither source is available or an image cannot be
loaded.

With `DJANGO_DEBUG=True`, Django serves media files during local development. Media storage and delivery must be configured separately for a production deployment. WhiteNoise serves static assets, not user-uploaded media files.

## Project checks

Check the Django configuration:

```powershell
python manage.py check
```

Run the automated tests:

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

- Complete profile pages and profile editing
- Display and moderation of review-reply threads
- Voting and management tools for review replies
- Expanded Wikidata synchronization
- Automatic movie-poster imports
- Backend-powered search suggestions and user search history
- Personalized movie recommendations
- PostgreSQL as the primary production database
- Production-ready container startup and deployment configuration
- Dedicated production media-file storage
- Additional tests for watch statuses, imports, profiles, and replies

## Project structure

- `accounts/` — authentication, custom users, profiles, and achievements
- `movies/` — catalog, movies, ratings, reviews, votes, and watch statuses
- `movies/services/` — Wikidata requests, parsing, and database imports
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
