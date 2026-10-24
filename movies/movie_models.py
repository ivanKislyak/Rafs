from django.db import models
from parler.models import TranslatableModel, TranslatedFields

class TypeOfWork(TranslatableModel):
    wikidata_id = models.CharField(max_length=20, unique=True)
    translations = TranslatedFields(
        name = models.CharField(max_length=200, blank=True)
    )
    banner_url = models.URLField(blank=True) 
    banner = models.ImageField(upload_to="typeofwork_covers/", blank=True, null=True)

    class Meta:
        verbose_name = "Type of Work"
        verbose_name_plural = "Types of Work"

    def __str__(self):
        return self.safe_translation_getter(
            "name",
            default=self.wikidata_id,
            any_language=True,
        )


class Genre(TranslatableModel):
    wikidata_id = models.CharField(max_length=20, unique=True)
    translations = TranslatedFields(
        name = models.CharField(max_length=200, blank=True)
    )
    banner_url = models.URLField(blank=True) 
    banner = models.ImageField(upload_to="genre_covers/", blank=True, null=True)

    class Meta:
        verbose_name = "Genre"
        verbose_name_plural = "Genres"

    def __str__(self):
        return self.safe_translation_getter(
            "name",
            default=self.wikidata_id,
            any_language=True,
        )
    
class Country(TranslatableModel):
    wikidata_id = models.CharField(max_length=20, unique=True)
    translations = TranslatedFields(
        name = models.CharField(max_length=200, blank=True)
    )
    banner_url = models.URLField(blank=True) 
    banner = models.ImageField(upload_to="country_covers/", blank=True, null=True)

    class Meta: 
        verbose_name = "Country"
        verbose_name_plural = "Countries"

    def __str__(self):
        return self.safe_translation_getter(
            "name",
            default=self.wikidata_id,
            any_language=True,
        )


class Studio(TranslatableModel):
    wikidata_id = models.CharField(max_length=20, unique=True)
    translations = TranslatedFields(
        name = models.CharField(max_length=200, blank=True)
    )
    logo_url = models.URLField(blank=True) 
    logo = models.ImageField(upload_to="studio_covers/", blank=True, null=True)

    class Meta:
        verbose_name = "Studio"
        verbose_name_plural = "Studios"

    def __str__(self):
        return self.safe_translation_getter(
            "name",
            default=self.wikidata_id,
            any_language=True,
        )


class Person(TranslatableModel):
    wikidata_id = models.CharField(max_length=20, unique=True)
    translations = TranslatedFields(
        name = models.CharField(max_length=200, blank=True),
        bio = models.TextField(verbose_name="Person Bio", blank=True)
    )
    photo_url = models.URLField(blank=True) 
    photo = models.ImageField(upload_to="person_covers/", blank=True, null=True)

    class Meta:
        verbose_name = "Person"
        verbose_name_plural = "Persons"

    def __str__(self):
        return self.safe_translation_getter(
            "name",
            default=self.wikidata_id,
            any_language=True,
        )
