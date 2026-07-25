from django.shortcuts import render
from django.views.generic import TemplateView
from movies.models import Movie

class HomePageView(TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["top_movies"] = (
            Movie.objects.filter(rate__isnull=False)
            .order_by("-rate", "name")[:5]
        )

        return context

# Create your views here.
