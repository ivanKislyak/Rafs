import json
import re
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.translation import gettext as _

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.contrib import messages
from django.contrib.contenttypes.prefetch import GenericPrefetch
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Avg, F, Count, Value, Prefetch, Q, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.template.loader import render_to_string
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from requests import RequestException

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics, permissions
from .forms import (
    MovieFilterForm, 
    ReviewForm, 
    ReviewReplyForm, 
    WikidataSearchForm
    )
from .models import (
    Movie, Review, ReviewReply,
    ReviewVote, WatchStatus,
    GlobalSearchIndex,
    )
from .serializers import (
    SearchResultSerializer, WatchStatusSerializer, 
    ReviewReplySerializer,
    )
from .services.wikidata import (
    search_wikidata_media, 
    fetch_movie_details_raw, 
    parse_movie_details,
    )
from .services.import_wikidata import import_parsed_data_to_db 
from core.utils import get_country_code

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
        
    page_obj = Paginator(all_movies, 25).get_page(request.GET.get("page"))
    
    next_page = (
        page_obj.next_page_number()
        if page_obj.has_next()
        else None
    )
    
    context = {
        "page_obj": page_obj,
        "filter_form": filter_form,
        "next_page": next_page,
    }

    if request.GET.get("format") == "json":
        html = render_to_string(
            "movies/_catalog_page.html",
            context,
            request=request,
        )
        return JsonResponse({
            "html": html,
            "next_page": next_page,
        })

    return render(request, "movies/catalog.html", context)

def movie_detail(request, movie_id):
    movie = get_object_or_404(Movie, pk=movie_id)
    replies = ReviewReply.objects.select_related("user").order_by("created_at")
    reviews = list(
        Review.objects.filter(movie=movie)
        .exclude(text="")
        .select_related("user")
        .prefetch_related(
            "votes",
            Prefetch("replies", queryset=replies, to_attr="loaded_replies"),
        )
    )
    user_already_rated_this = False
    watch_status = False

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
        watch_status = WatchStatus.objects.filter(movie=movie, user=request.user).first()

    try:
        open_replies_id = int(request.GET.get("replies", ""))
    except (TypeError, ValueError):
        open_replies_id = None

    return render(request, "movies/movie_detail.html",
                  {"movie": movie, 
                   "reviews": reviews,
                   "user_already_rated_this": user_already_rated_this,
                   "watch_status_model": WatchStatus,
                   "watch_status": watch_status,
                   "open_replies_id": open_replies_id})

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

            if is_new_review and not request.user.movies.filter(id=movie_id).exists():
                request.user.movies.add(movie)
                request.user.user_frames += 100
                request.user.save()
                messages.success(
                    request,
                    _("+100 Frames"),
                    extra_tags="frames-reward",
                )
            review.save()

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
        if not isinstance(data, dict):
            return JsonResponse({"error": _("Invalid data format")}, status=400)
        review_id = data.get("review_id")
        vote_value = int(data.get("vote_value"))

        if vote_value not in [ReviewVote.VoteChoice.LIKE, ReviewVote.VoteChoice.DISLIKE]:
            return JsonResponse({"error": _("Invalid vote value")}, status=400)

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
        return JsonResponse({"error": _("Invalid data format")}, status=400)


class SearchResultsListAPIView(generics.ListAPIView):
    serializer_class = SearchResultSerializer

    def get_queryset(self):
        raw_query = self.request.query_params.get('query', '').strip()
        words = re.findall(r'[^\W_]+', raw_query)
        query = None

        if words:
            tsquery = " & ".join(f"{word}:*" for word in words)
            query = (
                SearchQuery(tsquery, config="english", search_type="raw")
                | SearchQuery(tsquery, config="russian", search_type="raw")
                | SearchQuery(tsquery, config="spanish", search_type="raw")
                | SearchQuery(tsquery, config="german", search_type="raw")
            )

        if not query:
            return GlobalSearchIndex.objects.none()
            
        search_results = (GlobalSearchIndex.objects
                .filter(search_vector=query)
                .annotate(rank=SearchRank(F("search_vector"), query))
                .select_related('content_type')
                .prefetch_related(GenericPrefetch('content_object', [
                    Movie.objects.select_related('type_of_work').prefetch_related(
                        'type_of_work__translations',
                    ),
                ]))
                .order_by('-rank', "pk")
                )

        return search_results


def search_page(request):
    return render(request, 'movies/search_results.html', {
        'query': request.GET.get('query', '').strip(),
    })


class WatchStatusAPIView(APIView):
    serializer_class = WatchStatusSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, movie_id, *args, **kwargs):
        user = request.user
        movie = get_object_or_404(Movie, pk=movie_id)
        status_obj = WatchStatus.objects.filter(user=user, movie=movie).first()
        movie_status = getattr(status_obj, "status", None)
        return Response({"movie_id": movie_id, "status": movie_status})

    def put(self, request, movie_id: int):
        movie = get_object_or_404(Movie, pk=movie_id)
        serializer = WatchStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]

        instance, created = WatchStatus.objects.update_or_create(
            user=request.user,
            movie=movie,
            defaults={'status':new_status}
        )
        
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK

        return Response(
            {"movie_id": movie_id, "status": instance.status}, 
            status=status_code)

    def delete(self, request, movie_id: int):
        user = request.user
        movie = get_object_or_404(Movie, pk=movie_id)
        WatchStatus.objects.filter(user=user, movie=movie).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    

def show_popular_results(request):
    country_code = get_country_code(request)
    if country_code and not request.user.country_code:
        request.user.country_code = country_code
        request.user.save(update_fields=["country_code"])


@login_required
@require_POST
def set_movie_status(request):
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            return JsonResponse({"error": _("Invalid data format")}, status=400)

        movie_id = data.get("movie_id")
        status = data.get("status")

        if status not in WatchStatus.StatusChoice.values:
            return JsonResponse({"error": _("Invalid data format")}, status=400)

        movie = get_object_or_404(Movie, id=movie_id)
        user_status, created = WatchStatus.objects.get_or_create(
            user=request.user,
            movie=movie,
            defaults={"status": status},
        )

        if not created:
            if user_status.status == status:
                user_status.delete()
                current_user_status = None
            else:
                user_status.status = status
                user_status.save(update_fields=["status"])
                current_user_status = status
        else:
            current_user_status = status

        return JsonResponse({
            "movie_id": movie_id,
            "status": current_user_status or None,
        })

    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({"error": _("Invalid data format")}, status=400)

@login_required
@require_POST
def delete_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)
    if review.user_id != request.user.id and not request.user.is_superuser:
        raise PermissionDenied

    movie_id = review.movie_id

    review.delete()
    if request.POST.get("source") == "reviews":
        return redirect(_review_feed_return_url(request))
    return redirect("movies:detail", movie_id=movie_id)


@login_required
@require_POST
def delete_reply(request, reply_id):
    reply = get_object_or_404(
        ReviewReply.objects.select_related("review"),
        id=reply_id,
    )
    if reply.user_id != request.user.id and not request.user.is_superuser:
        raise PermissionDenied

    review_id = reply.review_id
    movie_id = reply.review.movie_id
    reply.delete()

    if request.POST.get("source") == "reviews":
        return redirect(_review_feed_return_url(request, review_id))

    detail_url = reverse("movies:detail", kwargs={"movie_id": movie_id})
    return redirect(f"{detail_url}?replies={review_id}#review-{review_id}")

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
        messages.error(request, _("The reply cannot be empty"))

    if request.POST.get("source") == "reviews":
        return redirect(_review_feed_return_url(request, review.id))
    detail_url = reverse("movies:detail", kwargs={"movie_id": review.movie_id})
    return redirect(f"{detail_url}?replies={review.id}#review-{review.id}")

class ReviewReplyListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = ReviewReplySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        review = get_object_or_404(Review, id=self.kwargs['review_id'])
        results = ReviewReply.objects.filter(review=review)
        return results

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

@staff_member_required
def wikidata_search(request):
    wd_search_form = WikidataSearchForm(request.GET or None)
    search_result = []
    search_error = False

    if wd_search_form.is_valid():
        query = wd_search_form.cleaned_data.get("query")
        lang = wd_search_form.cleaned_data.get("lang")

        try:
            search_result = search_wikidata_media(query=query, lang=lang, limit=10)
        except (RequestException, ValueError):
            search_error = True

    context = {
        "wd_search_form": wd_search_form,
        "search_result": search_result,
        "search_error": search_error,
    }

    return render(request, "movies/wd_search_form.html", context=context)

@staff_member_required
@require_POST
def wikidata_save_item(request, qid):
    raw = fetch_movie_details_raw(qid)
    parsed = parse_movie_details(raw, qid)
    imported = import_parsed_data_to_db(qid, parsed)
    return redirect("movies:detail", movie_id=imported.id)

def _review_feed_return_url(request, review_id=None):
    try:
        page = max(1, int(request.POST.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    url = f'{reverse("movies:show_reviews")}?page={page}'
    if review_id is not None:
        url += f"&replies={review_id}#review-{review_id}"
    return url


def show_reviews(request):
    # Slice in SQL before fetching authors, movies and replies.
    reviews = (
        Review.objects.select_related("user", "movie")
        .annotate(
            like_count=Count("votes", filter=Q(votes__value=1)),
            dislike_count=Count("votes", filter=Q(votes__value=-1)),
        )
        .exclude(text="")
        .order_by("-created_at", "-pk")
        .prefetch_related(Prefetch(
            "replies",
            queryset=ReviewReply.objects.select_related("user").order_by("created_at", "pk"),
            to_attr="loaded_replies",
        ))
    )
    if request.user.is_authenticated:
        user_vote = ReviewVote.objects.filter(
            review_id=OuterRef("pk"), user=request.user,
        ).values("value")[:1]
        reviews = reviews.annotate(user_vote=Coalesce(Subquery(user_vote), Value(0)))
    else:
        reviews = reviews.annotate(user_vote=Value(0))

    page_obj = Paginator(reviews, 10).get_page(request.GET.get("page"))
    try:
        open_replies_id = int(request.GET.get("replies", ""))
    except (TypeError, ValueError):
        open_replies_id = None
    context = {
        "reviews": page_obj.object_list,
        "page_obj": page_obj,
        "open_replies_id": open_replies_id,
    }
    if request.GET.get("format") == "json":
        return JsonResponse({
            "html": render_to_string("movies/_review_feed_page.html", context, request=request),
            "next_url": (
                f'{reverse("movies:show_reviews")}?page={page_obj.next_page_number()}'
                if page_obj.has_next() else None
            ),
        })
    return render(request, "movies/reviews.html", context)
