from django.contrib import admin
from .models import Movie, Review
from parler.admin import TranslatableAdmin

@admin.register(Movie)
class MovieAdmin(TranslatableAdmin):
    list_display = ["wikidata_id", 
                    "get_wikidata_name", "year", 
                    "get_studio"]

    def get_wikidata_name(self, obj):
        return obj.safe_translation_getter("wikidata_name", any_language=True)


    def get_studio(self, obj):
        first_studio = obj.studio.first()
        if first_studio:
            return first_studio.safe_translation_getter("wikidata_name", any_language=True)
        return "-"

@admin.register(Review)
class ReviewAdmin(TranslatableAdmin):
    list_display = ["user", 
                    "get_movie_name", "avg_rating", 
                    "text", "contains_spoiler", "created_at", 
                    "updated_at"]

    list_filter = ["created_at", "updated_at"]
    list_editable = ["contains_spoiler"]

    def get_wikidata_name(self, obj):
        return obj.safe_translation_getter("wikidata_name", any_language=True)

    def get_movie_name(self, obj):
        """Получает переведённое имя фильма из связанной модели Movie"""
        if obj.movie:
            return obj.movie.safe_translation_getter("wikidata_name", any_language=True)
        return "-"

admin.site.site_header = "RAFS - управление сайтом"
admin.site.site_title = "RAFS"
admin.site.index_title = "Фильмы, рецензии, профили"