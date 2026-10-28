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
    path('reply/<int:reply_id>/delete/', views.delete_reply, name='delete_reply'),
    path('wikidata/search/', views.wikidata_search, name='wikidata_search'),
    path('wikidata/items/<str:qid>/save/', views.wikidata_save_item, name='wikidata_save_item'),
    path('save/status/', views.set_movie_status, name='set_movie_status'),
    path('reviews/', views.show_reviews, name='show_reviews'),
    path('search/', views.search_page, name='search_query'),
    path('api/v1/search/', views.SearchResultsListAPIView.as_view(), name='search_results_api'),
    path('api/v1/watch-status/<int:movie_id>/', views.WatchStatusAPIView.as_view(), name='watch_status_api'),
    path('api/v1/reviews/<int:review_id>/replies/', views.ReviewReplyListCreateAPIView.as_view(), name='review_reply_api'),
    path('api/v1/replies/<int:reply_id>/', views.EditReplyAPIView.as_view(), name='edit_reply_api'),
]
