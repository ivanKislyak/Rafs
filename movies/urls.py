from django.urls import path

from . import views

app_name = "movies"

urlpatterns = [
    path("", views.catalog, name="catalog"),
    path("<int:movie_id>/", views.movie_detail, name="detail"),
    path("<int:movie_id>/review/", views.make_review_form, name="review_form")
]