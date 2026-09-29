from django.contrib import admin
from movies.models import (
    GlobalSearchIndex
)
from movies.movie_models import (
    TypeOfWork, Genre,
    Country, Studio,
    Person
)
from parler.admin import TranslatableAdmin


@admin.register(TypeOfWork)
class GenreAdmin(TranslatableAdmin):
    list_display = ('name', 'wikidata_id')

@admin.register(Genre)
class GenreAdmin(TranslatableAdmin):
    list_display = ('name', 'wikidata_id')

@admin.register(Country)
class GenreAdmin(TranslatableAdmin):
    list_display = ('name', 'wikidata_id')

@admin.register(Studio)
class GenreAdmin(TranslatableAdmin):
    list_display = ('name', 'wikidata_id')

@admin.register(Person)
class GenreAdmin(TranslatableAdmin):
    list_display = ('name', 'wikidata_id')


