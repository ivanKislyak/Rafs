from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = "movies"

urlpatterns = [
    path("", views.catalog, name="catalog"),
    path("test/", views.index, name="test"),
]