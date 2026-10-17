from django.urls import path, include
from django.views.generic import RedirectView

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("profile/", views.own_profile, name="own-profile"),
    path("profile/avatar/", views.update_avatar, name="update-avatar"),
    path(
        "profile/<str:username>/",
        RedirectView.as_view(pattern_name="profile", permanent=True),
        name="legacy-profile",
    ),
    path("moderation/apply/", views.moderation_application, name="moderation-application"),
    path(
        "moderation/applications/",
        views.moderation_applications_admin,
        name="moderation-applications-admin",
    ),
    path('api/v1/last-search-history', views.SearchHistoryListAPIView.as_view(), name='last_search_history')
]
