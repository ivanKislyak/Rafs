from django.urls import path, include

from . import views

app_name = "accounts"

urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),
    path("register/", views.register, name="register"),
    path("profile/", views.profile, name="profile")
]