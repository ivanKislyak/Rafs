from django.contrib.auth.decorators import login_required
from django.db.models import Avg, F, Count
from django.shortcuts import render, get_object_or_404, redirect
from .forms import MovieFilterForm, ReviewForm
from .models import Movie, Review

def catalog(request):
    filter_form = MovieFilterForm(request.GET or None)
    
    all_movies = (
        Movie.objects.annotate(reviews_count=Count("reviews"), review_avg_rating=Avg("reviews__avg_rating"))
        .order_by("-reviews_count", F("review_avg_rating").desc(nulls_last=True), "name")
    )

    if filter_form.is_valid():
        query = filter_form.cleaned_data.get("query")
        min_rating = filter_form.cleaned_data.get("min_rating")
        year_from = filter_form.cleaned_data.get("year_from")
        year_to = filter_form.cleaned_data.get("year_to")

        if query:
            all_movies = all_movies.filter(name__icontains=query)

        if min_rating is not None:
            all_movies = all_movies.filter(review_avg_rating__gte=min_rating)

        if year_from is not None:
            all_movies = all_movies.filter(year__gte=year_from)

        if year_to is not None:
            all_movies = all_movies.filter(year__lte=year_to)

    return render(request,"movies/catalog.html", context={"movie": all_movies, "filter_form": filter_form})

def movie_detail(request, movie_id):
    movie = get_object_or_404(Movie, pk=movie_id)
    reviews = Review.objects.filter(movie=movie).exclude(text="")
    user_already_rated_this = False

    if request.user.is_authenticated:
        user_already_rated_this = Review.objects.filter(movie=movie, user=request.user).first()
    return render(request, "movies/movie_detail.html",
                  {"movie": movie, 
                   "reviews": reviews,
                   "user_already_rated_this": user_already_rated_this})

@login_required
def make_review_form(request, movie_id):
    movie = get_object_or_404(Movie, pk=movie_id)
    review_form = ReviewForm()

    existing_review = Review.objects.filter(
        user = request.user,
        movie_id=movie_id).first()


    if request.method == "POST":
        review_form = ReviewForm(request.POST, instance=existing_review)

        if review_form.is_valid():
                review = review_form.save(commit=False)
                review.movie = movie
                review.user = request.user
                review.save()

                return redirect("movies:detail", movie_id=movie_id)

    if request.method == "GET":
        review_form = ReviewForm(instance=existing_review)
    
    return render(request, "movies/review_form.html", {"movie": movie, 
                       "review_form": review_form})
