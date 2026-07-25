from django.urls import path
from .views import HomePageView
from django.views.generic import TemplateView

app_name = "core"

urlpatterns = [
    path("", HomePageView.as_view(), name="home"),
    path("about_site/", TemplateView.as_view(template_name="core/about_site.html"), name="about")
]