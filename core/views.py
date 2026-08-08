from django.db.models import Avg, F, Count
from django.views.generic import TemplateView
from movies.models import Movie

class HomePageView(TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["top_movies"] = (
            Movie.objects.annotate(reviews_count=Count("reviews"), review_avg_rating=Avg("reviews__avg_rating"))
            .filter(review_avg_rating__isnull=False)
            .order_by("-reviews_count", F("review_avg_rating").desc(nulls_last=True), "name")[:10]
        )

        return context
