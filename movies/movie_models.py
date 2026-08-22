from django.db import models
from parler.models import TranslatableModel, TranslatedFields

class TypeOfWork(TranslatableModel):
    wikidata_id = models.CharField(max_length=20, unique=True)

    translations = TranslatedFields(
        name = models.CharField(max_length=200, blank=True)
    )

    def __str__(self):
        return self.safe_get_or_none('name') or self.wikidata_id


class Genre(TranslatableModel):
    wikidata_id = models.CharField(max_length=20, unique=True)

    translations = TranslatedFields(
        name = models.CharField(max_length=200, blank=True)
    )

    def __str__(self):
        return self.safe_get_or_none('name') or self.wikidata_id


class Country(TranslatableModel):
    wikidata_id = models.CharField(max_length=20, unique=True)

    translations = TranslatedFields(
        name = models.CharField(max_length=200, blank=True)
    )

    def __str__(self):
        return self.safe_get_or_none('name') or self.wikidata_id


class Studio(TranslatableModel):
    wikidata_id = models.CharField(max_length=20, unique=True)

    translations = TranslatedFields(
        name = models.CharField(max_length=200, blank=True)
    )

    def __str__(self):
        return self.safe_get_or_none('name') or self.wikidata_id


class Person(TranslatableModel):
    wikidata_id = models.CharField(max_length=20, unique=True)

    translations = TranslatedFields(
        name = models.CharField(max_length=200, blank=True)
    )

    def __str__(self):
        return self.safe_get_or_none('name') or self.wikidata_id




