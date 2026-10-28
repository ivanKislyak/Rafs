from django.contrib import admin
from django.db.models import Prefetch
from django.utils.translation import gettext_lazy as _
from .models import Movie, Review, ReviewReply, WatchStatus
from .movie_models import Studio
from parler.admin import TranslatableAdmin

@admin.register(Movie)
class MovieAdmin(TranslatableAdmin):
    list_display = ["wikidata_id", 
                    "get_wikidata_name", "year", 
                    "get_studio"]
    raw_id_fields = ("type_of_work", "genres", "countries", "studio",
                     "director", "screenwriter", "producer", "composer", "actors")
    search_fields = [
        "translations__wikidata_name",
        "name",
        "wikidata_id",
    ]
    list_filter = ['year']

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            "translations",
            Prefetch("studio", queryset=Studio.objects.order_by("pk").prefetch_related("translations")),
        )

    @admin.display(description=_("Movie Name"))
    def get_wikidata_name(self, obj):
        return obj.safe_translation_getter("wikidata_name", any_language=True) or obj.name or obj.wikidata_id


    @admin.display(description=_("Studio"))
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

    @admin.display(description=_("Movie"))
    def get_movie_name(self, obj):
        """Return the translated movie title from the related Movie instance."""
        if obj.movie:
            return obj.movie.safe_translation_getter("wikidata_name", any_language=True) or obj.movie.name or obj.movie.wikidata_id
        return "-"

    @admin.display(description=_("Review text"))
    def short_text(self, obj):
        if obj.text and len(obj.text) > 100:
            return f"{obj.text[:100]}..."
        return obj.text

@admin.register(ReviewReply)
class ReviewReplyAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'get_review_id', 'short_text', 'created_at']
    search_fields = ['user__username', 'text']
    list_filter = ['created_at']
    list_select_related = ('user',)
    raw_id_fields = ('user', 'review')
    readonly_fields = ('created_at',)

    @admin.display(description=_("Review ID"), ordering='review_id')
    def get_review_id(self, obj):
        return obj.review_id

    @admin.display(description=_("Reply text"))
    def short_text(self, obj):
        if len(obj.text) > 100:
            return f"{obj.text[:100]}..."
        return obj.text


@admin.register(WatchStatus)
class WatchStatusAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'movie', 'status']
    search_fields = ['user__username', 'movie__name', 'movie__translations__wikidata_name', 'movie__wikidata_id']
    list_filter = ['status']
    list_select_related = ('user', 'movie')
    raw_id_fields = ('user', 'movie')


admin.site.site_header = _("RAFS site administration")
admin.site.site_title = "RAFS"
admin.site.index_title = _("Movies, reviews and profiles")