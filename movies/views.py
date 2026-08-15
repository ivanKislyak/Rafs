import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, F, Count
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.http import HttpResponse

from .forms import MovieFilterForm, ReviewForm, ReviewReplyForm
from .models import Movie, Review, ReviewVote

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
    reviews = list(
        Review.objects.filter(movie=movie)
        .exclude(text="")
        .select_related("user")
        .prefetch_related("votes")
    )
    user_already_rated_this = False

    for review in reviews:
        review_votes = list(review.votes.all())
        review.like_count = sum(
            vote.value == ReviewVote.VoteChoice.LIKE for vote in review_votes
        )
        review.dislike_count = sum(
            vote.value == ReviewVote.VoteChoice.DISLIKE for vote in review_votes
        )
        review.user_vote = next(
            (
                vote.value
                for vote in review_votes
                if request.user.is_authenticated and vote.user_id == request.user.id
            ),
            0,
        )

    reviews.sort(key=lambda r: r.like_count - r.dislike_count, reverse=True)

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
            is_new_review = existing_review is None
            review = review_form.save(commit=False)
            review.movie = movie
            review.user = request.user

            if is_new_review:
                request.user.user_frames += 100
                request.user.save()

            review.save()

            if is_new_review:
                messages.success(
                    request,
                    "+100 Кадров",
                    extra_tags="frames-reward",
                )
            return redirect("movies:detail", movie_id=movie_id)

    if request.method == "GET":
        review_form = ReviewForm(instance=existing_review)
    
    return render(request, "movies/review_form.html", {"movie": movie, 
                       "review_form": review_form})

@login_required
@require_POST
def vote_review(request):
    try:
        data = json.loads(request.body)
        review_id = data.get("review_id")
        vote_value = int(data.get("vote_value"))

        if vote_value not in [ReviewVote.VoteChoice.LIKE, ReviewVote.VoteChoice.DISLIKE]:
            return JsonResponse({"error": "Неверное значение голоса"}, status=400)

        review = get_object_or_404(Review, id=review_id)
        vote, created = ReviewVote.objects.get_or_create(
            user=request.user,
            review=review,
            defaults={"value": vote_value},
        )

        if not created:
            if vote.value == vote_value:
                vote.delete()
                current_user_vote = 0
            else:
                vote.value = vote_value
                vote.save(update_fields=["value"])
                current_user_vote = vote_value
        else:
            current_user_vote = vote_value

        likes = review.votes.filter(value=ReviewVote.VoteChoice.LIKE).count()
        dislikes = review.votes.filter(value=ReviewVote.VoteChoice.DISLIKE).count()

        return JsonResponse({
            "likes": likes,
            "dislikes": dislikes,
            "user_vote": current_user_vote,
        })

    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({"error": "Неверный формат данных"}, status=400)

@login_required
@require_POST
def delete_review(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)
    movie_id = review.movie_id

    review.delete()
    return redirect("movies:detail", movie_id=movie_id)

@login_required
@require_POST
def reply_review(request, review_id):
    review = get_object_or_404(Review, pk=review_id)
    form = ReviewReplyForm(request.POST)

    if form.is_valid():
        reply = form.save(commit=False)
        reply.review = review
        reply.user = request.user
        reply.save()

    else:
        messages.error(request, "Ответ не может быть пустым")

    return redirect("movies:detail", movie_id=review.movie_id)