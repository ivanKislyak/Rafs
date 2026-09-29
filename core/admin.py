from django.contrib import admin
from movies.models import (
    GlobalSearchIndex
)
from movies.movie_models import (
    TypeOfWork, Genre,
    Country, Studio,
    Person
)

admin.site.register(TypeOfWork)
admin.site.register(Genre)
admin.site.register(Country)
admin.site.register(Studio)
admin.site.register(Person)

