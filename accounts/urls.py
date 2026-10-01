from django.urls import path, include

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("profile/", views.own_profile, name="own-profile"),
    path("profile/avatar/", views.update_avatar, name="update-avatar"),
    path("profile/<str:username>/", views.profile, name="profile"),
    path("moderation/apply/", views.moderation_application, name="moderation-application"),
    path(
        "moderation/applications/",
        views.moderation_applications_admin,
        name="moderation-applications-admin",
    ),
]
