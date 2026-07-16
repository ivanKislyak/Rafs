from django.http import HttpResponse
from django.shortcuts import render
from .forms import UserForm
from .forms import MovieFilterForm
import copy

list_of_movies = [
    {
        'id': 1,
        'name': 'Clean, Shaven',
        'year': 1993,
        'rate': 7.4,
        'description': "It follows Peter Winter, a schizophrenic man recently released from a mental institution, as he navigates terrifying sensory hallucinations and desperately tries to reclaim his daughter from her adoptive family",
        'path': 'clean_shaven.jpg'
    },

    {
        'id': 2,
        'name': 'Fight Club',
        'year': 1999,
        'rate': 10.0,
        'description': "It follows a disillusioned, insomniac office worker who—along with a charismatic soap salesman—founds an underground fight club that spirals into an anti-consumerist, anarchic terrorist organization",
        'path': None
    },

    {
        'id': 3,
        'name': 'Pi',
        'year': 1998,
        'rate': None,
        'description': "It follows Max Cohen, a paranoid mathematician who believes everything in nature can be understood through numbers. His obsession with finding a universal pattern leads him to build a supercomputer that uncovers a 216-digit number",
        'path': 'pi.jpg'
    },

    {
        'id': 4,
        'name': 'The Machinist',
        'year': 2004,
        'rate': None,
        'description': "It follows Trevor Reznik, an emaciated industrial worker who hasn't slept for an entire year. As severe insomnia pushes him to the edge of sanity, a horrific workplace accident triggers intense paranoia and a terrifying descent into his own repressed guilt",
        'path': 'the_machinist.jpg'
    }
]

def catalog(request):
    filter_form = MovieFilterForm(request.GET or None)
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

        if year_from and year_to:
            if year_to < year_from:
                filtered_movies = "Year Error"

    return render(request,"movies/catalog.html", context={"movies": filtered_movies, "filter_form": filter_form})

def index(request):
    if request.method == "POST":
        userform = UserForm(request.POST)
        if userform.is_valid():
            user_name = request.POST.get("name")
            age = request.POST.get("age")
            password = request.POST.get("password")
            return HttpResponse(f"<h2>Добро пожаловать, {user_name}, сегодня Вам {age}</h2>")
        else:
            return HttpResponse(f"Данные некорректны! Ошибки: {userform.errors}")
    else:
        userform = UserForm()
        return render(request, "tests/index.html", {"form": userform})

