from django.contrib import admin
from django.utils.translation import get_language
from .models import HomepageCollection, HomepageCollectionItem
from movies.models import GlobalSearchIndex
from movies.movie_models import (
    TypeOfWork, Genre,
    Country, Studio,
    Person
)
from parler.admin import TranslatableAdmin

@admin.register(Country)
class CountryAdmin(TranslatableAdmin):
    list_display = ('name', 'wikidata_id')
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.translated(get_language()).order_by('translations__name').distinct()


@admin.register(Genre)
class GenreAdmin(TranslatableAdmin):
    list_display = ('name', 'wikidata_id')
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.translated(get_language()).order_by('translations__name').distinct()


@admin.register(Studio)
class StudioAdmin(TranslatableAdmin):
    list_display = ('name', 'wikidata_id')
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.translated(get_language()).order_by('translations__name').distinct()


@admin.register(Person)
class PersonAdmin(TranslatableAdmin):
    list_display = ('name', 'wikidata_id')
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.translated(get_language()).order_by('translations__name').distinct()


@admin.register(TypeOfWork)
class TypeOfWorkAdmin(TranslatableAdmin):
    list_display = ('name', 'wikidata_id')
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.translated(get_language()).order_by('translations__name').distinct()
        
@admin.register(HomepageCollection)
class HomepageCollectionAdmin(TranslatableAdmin):
    list_display = ('position', 'title', 'is_published')
    list_editable = ('is_published',)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.translated(get_language()).order_by('translations__title').distinct()

@admin.register(HomepageCollectionItem)
class HomepageCollectionItemAdmin(admin.ModelAdmin):
    list_display = ('collection', 'movie', 'position')
    list_editable = ['position']
    
    # def get_queryset(self, request):
    #     qs = super().get_queryset(request)
    #     return qs.translated(get_language()).order_by('translations__title').distinct()

    # @admin.display(description=_("Collection"))
    # def get_movie_name(self, obj):
    #     """Return the translated movie title from the related Movie instance."""
    #     if obj.movie:
    #         return obj.movie.safe_translation_getter("wikidata_name", any_language=True) or obj.movie.name or obj.movie.wikidata_id
    #     return "-"