from rest_framework import generics, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.decorators import action

from django.forms import model_to_dict
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, IntegerField, OuterRef, Prefetch, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.formats import get_format

from movies.models import Review, ReviewReply, WatchStatus

from .forms import AvatarUpdateForm, RegisterUserForm
from .models import Achievement, User, SearchHistory
from .serializers import SearchHistorySerializer, MeSerializer

def register(request):
    if request.method == "POST":
            register_form = RegisterUserForm(request.POST)
            if register_form.is_valid():
                user = register_form.save()
                login(request, user)
                return redirect("movies:catalog")
    else:
        register_form = RegisterUserForm()

    return render(request, "accounts/register.html", {"register_form": register_form})


def profile(request, username):
    review_count = (
        Review.objects.filter(user_id=OuterRef("pk"))
        .values("user_id")
        .annotate(total=Count("id"))
        .values("total")
    )
    reply_count = (
        ReviewReply.objects.filter(user_id=OuterRef("pk"))
        .values("user_id")
        .annotate(total=Count("id"))
        .values("total")
    )
    profile_user = get_object_or_404(
        User.objects.filter(is_deleted=False)
        .annotate(
            review_count=Coalesce(
                Subquery(review_count, output_field=IntegerField()),
                Value(0),
            ),
            reply_count=Coalesce(
                Subquery(reply_count, output_field=IntegerField()),
                Value(0),
            ),
        )
        .prefetch_related(
            Prefetch(
                "achievement",
                queryset=Achievement.objects.only(
                    "id", "name", "description", "badge_image", "display_in_profile", "starts_at", "ends_at", "created_at"
                ).filter(display_in_profile=True),
                to_attr="profile_achievements",
            )
        ),
        username=username,
    )

    grouped_statuses = {
        status_value: []
        for status_value, _status_label in WatchStatus.StatusChoice.choices
    }
    watch_status_objects = (
        WatchStatus.objects.filter(user=profile_user)
        .select_related("movie")
        .prefetch_related("movie__translations")
        .order_by("movie__name", "movie_id")
    )
    for watch_status in watch_status_objects:
        movie = watch_status.movie
        titles = {
            row.language_code: row.wikidata_name.strip()
            for row in movie.translations.all()
        }
        languages = [movie.get_current_language(), *movie.get_fallback_languages()]
        watch_status.movie_title = (
            next((titles[code] for code in languages if titles.get(code)), None)
            or movie.name.strip() or movie.wikidata_id or _("Untitled")
        )
        grouped_statuses[watch_status.status].append(watch_status)

    watch_statuses = [
        {
            "value": status_value,
            "label": status_label,
            "count": len(grouped_statuses[status_value]),
            "movies": grouped_statuses[status_value],
        }
        for status_value, status_label in WatchStatus.StatusChoice.choices
    ]
    is_owner = request.user.is_authenticated and request.user.pk == profile_user.pk

    return render(
        request,
        "accounts/profile.html",
        {
            "profile_user": profile_user,
            "is_owner": is_owner,
            "profile_role": _("Newcomer"),
            "watch_statuses": watch_statuses,
            "library_number_grouping": get_format("NUMBER_GROUPING"),
            "library_thousand_separator": get_format("THOUSAND_SEPARATOR"),
            "avatar_form": AvatarUpdateForm(instance=profile_user) if is_owner else None,
            "profile_sex_choices": User.SexChoice.choices if is_owner else (),
        },
    )


@login_required
def update_avatar(request):
    if request.method != "POST":
        return redirect("profile", username=request.user.username)

    if request.POST.get("avatar_action") == "delete":
        old_avatar = request.user.avatar_image
        request.user.avatar_image = None
        request.user.save(update_fields=["avatar_image"])
        if old_avatar:
            old_avatar.delete(save=False)
        messages.success(request, _("Avatar removed"))
        return redirect("profile", username=request.user.username)

    old_avatar_name = request.user.avatar_image.name if request.user.avatar_image else ""
    old_avatar_storage = request.user.avatar_image.storage
    form = AvatarUpdateForm(request.POST, request.FILES, instance=request.user)
    if form.is_valid():
        updated_user = form.save()
        if old_avatar_name and old_avatar_name != updated_user.avatar_image.name:
            old_avatar_storage.delete(old_avatar_name)
        messages.success(request, _("Avatar updated"))
    else:
        error_text = " ".join(
            error
            for field_errors in form.errors.values()
            for error in field_errors
        )
        messages.error(request, error_text or _("Could not update the avatar"))

    return redirect("profile", username=request.user.username)


class SearchHistoryViewSet(viewsets.ModelViewSet):
    serializer_class = SearchHistorySerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return SearchHistory.objects.filter(user=self.request.user).order_by('-updated_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        query_text = serializer.validated_data['query']
        
        instance, created = SearchHistory.objects.update_or_create(
            user=request.user,
            query=query_text,
            defaults={}
        )
        
        serializer = self.get_serializer(instance)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=status_code)

class SearchHistoryAPIList(generics.ListCreateAPIView):
    serializer_class = SearchHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SearchHistory.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class SearchHistoryAPIUpdate(generics.UpdateAPIView):
    serializer_class = SearchHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SearchHistory.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class SearchHistoryAPIDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SearchHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SearchHistory.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)    
        

class MeAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user