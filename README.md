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
- Shared header and footer templates with component-based CSS

## Technologies

- Python 3.11+
- Django 5.2.16
- SQLite for local development
- PostgreSQL support through psycopg
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

## Running locally

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

The local `db.sqlite3` database and the entire `media/` directory are excluded by `.gitignore`. A fresh clone therefore does not include the movies, users, ratings, or reviews from the development database.

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
- Personalized movie recommendations
- Full user-interface localization
- PostgreSQL as the primary production database
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
- `media/` — user-uploaded files excluded from the repository
- `config/` — settings and root URL configuration

## License

The source code is available under the PolyForm Noncommercial
License 1.0.0.

Running a paid or advertising-supported derivative service requires
prior written permission.

The RAFS name, logo, and wasp mascot are not included in the software
license. See `BRAND_ASSETS.md`.

Movie posters, fonts, and other third-party materials remain the
property of their respective owners.
