from django.urls import path, include
from django.views.generic import RedirectView
from rest_framework import routers

from . import views

app_name = "accounts"

router = routers.DefaultRouter()
router.register(r'search-history', views.SearchHistoryViewSet, basename='searchhistory')

urlpatterns = [
    path("register/", views.register, name="register"),
    path("profile/avatar/", views.update_avatar, name="update-avatar"),
    path("api/v1/", include(router.urls)),
    path('api/v1/me/', views.MeAPIView.as_view(), name='me'),
    path('api/v1/me/username/', views.UsernameSettingsAPIView.as_view(), name='me-username'),
    path('api/v1/me/settings/', views.ProfileSettingsAPIView.as_view(), name='profile-settings-api'),
    path('api/v1/me/email/', views.EmailSettingsAPIView.as_view(), name='me-email'),
]
