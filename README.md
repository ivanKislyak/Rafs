# RAFS

RAFS is a Django web application for discovering, rating, and reviewing movies.

The project is currently in active development.

## Current features

- Movie catalog
- Search by movie title
- Filtering by rating and release year
- Form validation with Django Forms
- Reusable Django templates
- Local static files and movie posters

## Planned features

- Movie detail pages
- User registration and profiles
- Ratings and reviews
- PostgreSQL database
- Movie data from an external API
- Personal recommendations

## Technologies

- Python
- Django
- HTML
- Django Template Language
- SQLite

## Running locally

Clone the repository:

```bash
git clone https://github.com/ivanKislyak/Rafs.git
cd Rafs
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```powershell
.venv\Scripts\activate
```

Install Django and run the project:

```powershell
pip install Django==5.2.16
python manage.py migrate
python manage.py runserver
```

Open the following address in your browser:

```text
http://127.0.0.1:8000/movies/
```

## Status

This is an educational portfolio project. New features are added as I continue learning Django.