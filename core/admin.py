from django.contrib import admin
from django.utils.translation import get_language
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