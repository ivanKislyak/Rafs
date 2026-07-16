from django.http import JsonResponse, HttpResponse, HttpResponseNotFound, HttpResponseForbidden, HttpResponseBadRequest, HttpResponseRedirect, HttpResponsePermanentRedirect
from django.shortcuts import render
from django.core.serializers.json import DjangoJSONEncoder
from django.template.response import TemplateResponse
from datetime import datetime

def index(request, number=666):
    data = {"n": number}
    return render(request, "accounts/index.html", context={"data": data, "dada": {'id is': data['n']*2}})

class Person:

    def __init__(self, name):
        self.name = name  # имя человека

# установка куки
def set(request):
    # получаем из строки запроса имя пользователя
    username = request.GET.get("username", "Undefined")
    response = HttpResponse(f"Hello {username}")
    # передаем его в куки
    response.set_cookie("username", username)
    return response

def about(request):
    return render(request, "accounts/about.html")

# получение куки
def get(request):
    # получаем куки с ключом username
    username = request.COOKIES["username"]
    return HttpResponse(f"Hello {username}")

class Person54:

    def __init__(self, name, age):
        self.name = name  # имя человека
        self.age = age  # возраст человека


class Person54Encoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, Person54):
            return {"name": obj.name, "age": obj.age}
            # return obj.__dict__
        return super().default(obj)


def kislyak(request):
    page_data = {
        "heading": "Это Кисляк",
        "description": "Первая страница Rafs, созданная через Django-шаблон.",
    }

    return render(request, "accounts/kislyak.html", page_data)

def access(request, age):
    # если возраст НЕ входит в диапазон 1-110, посылаем ошибку 400
    if age not in range(1, 111):
        return HttpResponseBadRequest("Некорректные данные")
    # если возраст больше 17, то доступ разрешен
    if (age > 17):
        return HttpResponse("Доступ разрешен")
    # если нет, то возвращаем ошибку 403
    else:
        return HttpResponseForbidden("Доступ заблокирован: недостаточно лет")


def contact(request):
    return render(request, "accounts/contact.html", context={"my_date": datetime.now()})
