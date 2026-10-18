from django.urls import path, include
from django.views.generic import RedirectView

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("profile/avatar/", views.update_avatar, name="update-avatartar"),
    path('api/v1/last-search-history/', views.SearchHistoryListAPIView.as_view(), name='last-search-history'),
    path('api/v1/last-search-history/<int:pk>/', views.SearchHistoryListAPIView.as_view(), name='last-search-history'),
]
