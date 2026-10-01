from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, IntegerField, OuterRef, Prefetch, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from movies.models import Review, ReviewReply, WatchStatus

from .forms import AvatarUpdateForm, ModerationApplicationForm, RegisterUserForm
from .models import Achievement, ModerationApplication, User

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

@login_required
def own_profile(request):
    return redirect("accounts:profile", username=request.user.username)


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
                queryset=Achievement.objects.only("id", "name", "description"),
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
        .order_by("movie__name", "movie_id")
    )
    for watch_status in watch_status_objects:
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
            "avatar_form": AvatarUpdateForm(instance=profile_user) if is_owner else None,
        },
    )


@login_required
def update_avatar(request):
    if request.method != "POST":
        return redirect("accounts:profile", username=request.user.username)

    if request.POST.get("avatar_action") == "delete":
        old_avatar = request.user.avatar_image
        request.user.avatar_image = None
        request.user.save(update_fields=["avatar_image"])
        if old_avatar:
            old_avatar.delete(save=False)
        messages.success(request, _("Avatar removed."))
        return redirect("accounts:profile", username=request.user.username)

    old_avatar_name = request.user.avatar_image.name if request.user.avatar_image else ""
    old_avatar_storage = request.user.avatar_image.storage
    form = AvatarUpdateForm(request.POST, request.FILES, instance=request.user)
    if form.is_valid():
        updated_user = form.save()
        if old_avatar_name and old_avatar_name != updated_user.avatar_image.name:
            old_avatar_storage.delete(old_avatar_name)
        messages.success(request, _("Avatar updated."))
    else:
        error_text = " ".join(
            error
            for field_errors in form.errors.values()
            for error in field_errors
        )
        messages.error(request, error_text or _("Could not update the avatar."))

    return redirect("accounts:profile", username=request.user.username)


@login_required
def moderation_application(request):
    application = ModerationApplication.objects.filter(user=request.user).first()

    if request.method == "POST" and application is None:
        form = ModerationApplicationForm(request.POST)
        if form.is_valid():
            application = form.save(commit=False)
            application.user = request.user
            application.save()
            messages.success(request, _("Your application has been sent."))
            return redirect("accounts:moderation-application")
    else:
        form = ModerationApplicationForm(initial={"email": request.user.email})

    return render(
        request,
        "accounts/moderation_application.html",
        {"application": application, "form": form},
    )


@login_required
def moderation_applications_admin(request):
    if not request.user.is_superuser:
        raise PermissionDenied

    applications = ModerationApplication.objects.select_related("user").all()
    return render(
        request,
        "accounts/moderation_applications_admin.html",
        {"applications": applications},
    )
