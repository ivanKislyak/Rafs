# RAFS

<p align="center">
  <img src="static/images/rafs-preview-v3.png" alt="RAFS wasp mascot" width="760">
</p>

RAFS is a Django web application for discovering, rating, and discussing movies.

The project is currently in active development and is being built as an educational portfolio project.

## Current features

- Home page with top movies ranked by review activity and average score
- Movie catalog with title search and rating/year filters
- User registration, login, and POST-based logout
- User avatars, levels, and Frames — the RAFS experience points
- Movie ratings based on an overall score and optional additional criteria
- Written reviews with spoiler warnings
- Like and dislike reactions without reloading the page
- A 100-Frame reward for the first review of a movie
- Average movie ratings calculated from user reviews
- Movie cover uploads through a Django `ImageField`

## Technologies

- Python 3.11+
- Django 5.2.16
- SQLite
- Django ORM and Django Template Language
- HTML, CSS, and JavaScript
- Pillow for image handling
- python-dotenv for environment variables
- WhiteNoise for static files

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
DEBUG=True
```

Apply the migrations and start the development server:

```powershell
python manage.py migrate
python manage.py runserver
```

The following pages will then be available:

- Home page: <http://127.0.0.1:8000/>
- Movie catalog: <http://127.0.0.1:8000/movies/>
- Django admin: <http://127.0.0.1:8000/admin/>

## Local data and movie covers

The local `db.sqlite3` database and the entire `media/` directory are excluded by `.gitignore`. A fresh clone therefore does not include the movies, users, ratings, or reviews from the development database.

Movie covers are not currently distributed with the repository either. They must be uploaded manually:

1. Create an administrator account:

   ```powershell
   python manage.py createsuperuser
   ```

2. Open <http://127.0.0.1:8000/admin/>.
3. Create or edit a movie and upload an image through its `cover` field.

Django stores uploaded covers in `media/movie_covers/` and saves the associated path in the database. Copying an image into that directory alone is not enough: the file must also be assigned to the appropriate movie through the `cover` field. The site displays a default placeholder when a cover is not assigned or its file is missing.

With `DEBUG=True`, Django serves media files during local development. Media storage and delivery must be configured separately for a production deployment. WhiteNoise serves static assets, not user-uploaded media files.

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

- Full profile pages and profile editing
- Automatic movie data and cover imports
- Movie recommendations
- Migration from SQLite to PostgreSQL
- Dedicated media-file storage
- Production deployment with HTTPS

## Project structure

- `accounts/` — authentication and user data
- `movies/` — catalog, movies, ratings, reviews, and reactions
- `core/` — home page and general site pages
- `templates/` — shared Django templates
- `static/` — CSS, JavaScript, logos, and interface assets
- `media/` — uploaded images excluded from the repository
- `config/` — Django settings and root URL configuration

## License

The source code is available under the PolyForm Noncommercial
License 1.0.0.

Running a paid or advertising-supported derivative service requires
prior written permission.

The RAFS name, logo, and wasp mascot are not included in the software
license. See `BRAND_ASSETS.md`.

Movie posters, fonts, and other third-party materials remain the
property of their respective owners.
