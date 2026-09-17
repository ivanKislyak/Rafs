from django.urls import path, include
from . import views

app_name = "movies"

urlpatterns = [
    path("", views.catalog, name="catalog"),
    path('i18n/', include('django.conf.urls.i18n')),
    path("<int:movie_id>/", views.movie_detail, name="detail"),
    path("review/<int:movie_id>/", views.make_review_form, name="review_form"),
    path('review/vote/', views.vote_review, name='vote_review'),
    path('review/<int:review_id>/delete_review/', views.delete_review, name='delete_review'),
    path('review/<int:review_id>/reply/', views.reply_review, name='reply_review'),
    path('wikidata/search/', views.wikidata_search, name='wikidata_search'),
    path('wikidata/items/<str:qid>/save/', views.wikidata_save_item, name='wikidata_save_item'),
    path('save/status/', views.set_movie_status, name='set_movie_status'),
    path('reviews/', views.show_reviews, name='show_reviews'),
    path('results/', views.show_search_results, name='show_search_results')
]