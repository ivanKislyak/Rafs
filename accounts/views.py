from django.http import HttpResponse
from django.shortcuts import render


def index(request):
    return HttpResponse("Hello, world. You're at the polls index.")

def kislyak(request):
    page_data = {
        "heading": "Это Кисляк",
        "description": "Первая страница Rafs, созданная через Django-шаблон.",
    }

    return render(request, "accounts/kislyak.html", page_data)


def contact(request):
    return HttpResponse("Контакты: +7 777 777 7777")