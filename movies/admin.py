from django.contrib import admin
from django.db.models import Prefetch
from .models import Movie, Review
from .movie_models import Studio
from parler.admin import TranslatableAdmin

@admin.register(Movie)
class MovieAdmin(TranslatableAdmin):
    list_display = ["wikidata_id", 
                    "get_wikidata_name", "year", 
                    "get_studio"]
    raw_id_fields = ("type_of_work", "genres", "countries", "studio",
                     "director", "screenwriter", "producer", "composer", "actors")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            "translations",
            Prefetch("studio", queryset=Studio.objects.order_by("pk").prefetch_related("translations")),
        )

    def get_wikidata_name(self, obj):
        return obj.safe_translation_getter("wikidata_name", any_language=True) or obj.name or obj.wikidata_id


    def get_studio(self, obj):
        first_studio = obj.studio.first()
        if first_studio:
            return first_studio.safe_translation_getter("name", any_language=True) or first_studio.wikidata_id
        return "-"

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["user", 
                    "get_movie_name", "avg_rating", 
                    "short_text", "contains_spoiler", "created_at", 
                    "updated_at"]

    list_filter = ["created_at", "updated_at"]
    list_editable = ["contains_spoiler"]
    raw_id_fields = ("movie",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "movie").prefetch_related("movie__translations")

    def get_wikidata_name(self, obj):
        return obj.safe_translation_getter("wikidata_name", any_language=True)

    def get_movie_name(self, obj):
        """Получает переведённое имя фильма из связанной модели Movie"""
        if obj.movie:
            return obj.movie.safe_translation_getter("wikidata_name", any_language=True) or obj.movie.name or obj.movie.wikidata_id
        return "-"

    @admin.display(description='Текст отзыва')
    def short_text(self, obj):
        if obj.text and len(obj.text) > 100:
            return f"{obj.text[:100]}..."
        return obj.text

admin.site.site_header = "RAFS - управление сайтом"
admin.site.site_title = "RAFS"
admin.site.index_title = "Фильмы, рецензии, профили"