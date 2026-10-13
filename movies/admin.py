from django.contrib import admin
from .models import Movie, Review
from parler.admin import TranslatableAdmin

admin.site.register(Movie)

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

admin.site.register(Review)
