from django.urls import path

from . import views

app_name = "feedback"

# Included once at the site root, so the page and the API share the "feedback" namespace.
urlpatterns = [
    path("feedback/", views.feedback_page, name="page"),
    path("api/v1/feedback/", views.FeedbackCreateAPIView.as_view(), name="feedback_api"),
]
