from django.urls import path

from . import views

app_name = "movies"

urlpatterns = [
    path("", views.catalog, name="catalog"),
    path("<int:movie_id>/", views.movie_detail, name="detail"),
    path("review/<int:movie_id>/", views.make_review_form, name="review_form"),
    path('review/vote/', views.vote_review, name='vote_review'),
    path('review/<int:id>/delete_review/', views.delete_review, name='delete_review'),
    path('review/<int:id>/reply/', views.reply_review, name='reply_review'),
]