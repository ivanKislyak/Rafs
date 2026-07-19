from django.shortcuts import render
from .forms import MovieFilterForm
from .models import Movie

def catalog(request):
    filter_form = MovieFilterForm(request.GET or None)

    all_movies = Movie.objects.all()

    if filter_form.is_valid():
        query = filter_form.cleaned_data.get("query")
        min_rating = filter_form.cleaned_data.get("min_rating")
        year_from = filter_form.cleaned_data.get("year_from")
        year_to = filter_form.cleaned_data.get("year_to")


        if query:
            all_movies = all_movies.filter(name__icontains=query)

        if min_rating is not None:
            all_movies = all_movies.filter(rate__gte=min_rating)

        if year_from is not None:
            all_movies = all_movies.filter(year__gte=year_from)

        if year_to is not None:
            all_movies = all_movies.filter(year__lte=year_to)

    return render(request,"movies/catalog.html", context={"movies": all_movies, "filter_form": filter_form})

