import os
import json

from django.conf import settings
from django.shortcuts import render
from .forms import MovieFilterForm
from .models import Movie
import asyncio

def get_local_movies() -> list:
    file_path = os.path.join(settings.BASE_DIR, 'movies', 'movies.json')
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    except FileNotFoundError:
        print("ничего нема")
        return []

def catalog(request):
    filter_form = MovieFilterForm(request.GET or None)
    list_of_movies = get_local_movies()

    filtered_movies = [m.copy() for m in list_of_movies]

    if filter_form.is_valid():
        query = filter_form.cleaned_data.get("query")
        min_rating = filter_form.cleaned_data.get("min_rating")
        year_from = filter_form.cleaned_data.get("year_from")
        year_to = filter_form.cleaned_data.get("year_to")

        if query:
            filtered_movies = [m for m in filtered_movies if query.casefold() in m.get("name", "").casefold()]

        if min_rating:
            filtered_movies = [m for m in filtered_movies if (m.get("rate") or 0.0) >= min_rating]

        if year_from:
            filtered_movies = [m for m in filtered_movies if m.get("year", 0) >= year_from]

        if year_to:
            filtered_movies = [m for m in filtered_movies if m.get("year", 0) <= year_to]

    return render(request,"movies/catalog.html", context={"movies": filtered_movies, "filter_form": filter_form})

