from django.http import JsonResponse, HttpResponse, HttpResponseNotFound, HttpResponseForbidden, HttpResponseBadRequest, HttpResponseRedirect, HttpResponsePermanentRedirect
from django.shortcuts import render, redirect
from django.core.serializers.json import DjangoJSONEncoder
from django.template.response import TemplateResponse
from datetime import datetime
from django.contrib.auth import login
from .forms import RegisterUserForm

def register(request):
    if request.method == "POST":
            register_form = RegisterUserForm(request.POST)
            if register_form.is_valid():
                user = register_form.save()
                login(request, user)
                return redirect("movies:catalog")
    else:
        register_form = RegisterUserForm()

    return render(request, "accounts/register.html", {"register_form": register_form})

