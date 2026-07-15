"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path, re_path, include
from django.views.generic import TemplateView

"""urlpatterns = [
    path("6index/<int:number>/", views.index),
    re_path(r"^6set/$", views.set),
    path("6get", views.get),
    path("6about/", views.about),
    path("6contact/", views.contact),
    path("6access/<int:age>/", views.access),
    re_path(r'^6kislyak/$', views.kislyak),
    path('6base54/', TemplateView.as_view(template_name="testtemplate.html")),
    # path('', TemplateView.as_view(template_name="secondtest.html"))
]""" # tests

urlpatterns = [
    path("", TemplateView.as_view(template_name="base.html")),
    path("movies/", include("movies.urls")),
    path("about_site/", TemplateView.as_view(template_name="about_site.html"), name="about"),
]