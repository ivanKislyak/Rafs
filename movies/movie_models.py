from django.db import models
from parler.models import TranslatableModel, TranslatedFields
from django.utils.translation import gettext_lazy as _

class TypeOfWork(TranslatableModel):
    wikidata_id = models.CharField(max_length=20, unique=True, verbose_name=_("ID on wikidata.org"))
    translations = TranslatedFields(
        name = models.CharField(max_length=200, blank=True, verbose_name=_("Name"))
    )
    banner_url = models.URLField(blank=True, verbose_name=_("Banner URL"))
    banner = models.ImageField(upload_to="typeofwork_covers/", blank=True, null=True, verbose_name=_("Banner"))

    class Meta:
        verbose_name = _("Type of Work")
        verbose_name_plural = _("Types of Work")

    def __str__(self):
        return self.safe_translation_getter(
            "name",
            default=self.wikidata_id,
            any_language=True,
        )


class Genre(TranslatableModel):
    wikidata_id = models.CharField(max_length=20, unique=True, verbose_name=_("ID on wikidata.org"))
    translations = TranslatedFields(
        name = models.CharField(max_length=200, blank=True, verbose_name=_("Name"))
    )
    banner_url = models.URLField(blank=True, verbose_name=_("Banner URL"))
    banner = models.ImageField(upload_to="genre_covers/", blank=True, null=True, verbose_name=_("Banner"))

    class Meta:
        verbose_name = _("Genre")
        verbose_name_plural = _("Genres")

    def __str__(self):
        return self.safe_translation_getter(
            "name",
            default=self.wikidata_id,
            any_language=True,
        )
    
class Country(TranslatableModel):
    wikidata_id = models.CharField(max_length=20, unique=True, verbose_name=_("ID on wikidata.org"))
    translations = TranslatedFields(
        name = models.CharField(max_length=200, blank=True, verbose_name=_("Name"))
    )
    banner_url = models.URLField(blank=True, verbose_name=_("Banner URL"))
    banner = models.ImageField(upload_to="country_covers/", blank=True, null=True, verbose_name=_("Banner"))

    class Meta: 
        verbose_name = _("Country")
        verbose_name_plural = _("Countries")

    def __str__(self):
        return self.safe_translation_getter(
            "name",
            default=self.wikidata_id,
            any_language=True,
        )


class Studio(TranslatableModel):
    wikidata_id = models.CharField(max_length=20, unique=True, verbose_name=_("ID on wikidata.org"))
    translations = TranslatedFields(
        name = models.CharField(max_length=200, blank=True, verbose_name=_("Name"))
    )
    logo_url = models.URLField(blank=True, verbose_name=_("Logo URL"))
    logo = models.ImageField(upload_to="studio_covers/", blank=True, null=True, verbose_name=_("Logo"))

    class Meta:
        verbose_name = _("Studio")
        verbose_name_plural = _("Studios")

    def __str__(self):
        return self.safe_translation_getter(
            "name",
            default=self.wikidata_id,
            any_language=True,
        )


class Person(TranslatableModel):
    wikidata_id = models.CharField(max_length=20, unique=True, verbose_name=_("ID on wikidata.org"))
    translations = TranslatedFields(
        name = models.CharField(max_length=200, blank=True, verbose_name=_("Person name")),
        bio = models.TextField(verbose_name=_("Person Bio"), blank=True)
    )
    photo_url = models.URLField(blank=True, verbose_name=_("Photo URL"))
    photo = models.ImageField(upload_to="person_covers/", blank=True, null=True, verbose_name=_("Photo"))

    class Meta:
        verbose_name = _("Person")
        verbose_name_plural = _("Persons")

    def __str__(self):
        return self.safe_translation_getter(
            "name",
            default=self.wikidata_id,
            any_language=True,
        )
