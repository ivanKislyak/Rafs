from django.db import models
from movies.models import Movie
from parler.models import TranslatableModel, TranslatedFields
from django.utils.translation import gettext_lazy as _

class HomepageCollection(TranslatableModel):
    translations = TranslatedFields(
        title = models.CharField(
            verbose_name=_("Title of Homepage Collection"),
            max_length=200,
            blank=False
        )
    )
    is_published = models.BooleanField(default=False)
    position = models.SmallIntegerField(blank=False)

    class Meta:
        verbose_name = _('Homepage Collection')
        verbose_name_plural = _('Homepage Collections')

    def __str__(self):
        return self.safe_translation_getter(
            "title",
            default=position,
            any_language=True
        )
    

class HomepageCollectionItem(models.Model):
    collection = models.ManyToManyField(
        HomepageCollection,
        related_name='items'
    )
    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE,
        related_name='homepage_item'
    )
    position = models.SmallIntegerField(blank=False)

    class Meta:
        ordering = ['position', 'pk']
        verbose_name = _('Homepage Collection Item')
        verbose_name_plural = _('Homepage Collection Items')

    def __str__(self):
        return f"{
            self.movie.safe_translation_getter(
            "wikidata_name",
            default=self.position,
            any_language=True
        )}"

    

