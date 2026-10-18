from django.urls import path, include
from django.views.generic import RedirectView
from rest_framework import routers

from . import views

app_name = "accounts"

router = routers.SimpleRouter()
router.register(r'last-search-history', views.SearchHistoryViewSet, basename='searchhistory')

urlpatterns = [
    path("register/", views.register, name="register"),
    path("profile/avatar/", views.update_avatar, name="update-avatartar"),
    path("api/v1/", include(router.urls))
    # path('api/v1/last-search-history/', views.SearchHistoryViewSet.as_view({'get': 'list'}), name='last-search-history'),
    # path('api/v1/last-search-history/<int:pk>/', views.SearchHistoryViewSet.as_view({'put': 'update'}), name='last-search-history'),
    # path('api/v1/last-search-history-detail/<int:pk>/', views.SearchHistoryAPIDetailView.as_view(), name='last-search-history'),
]
