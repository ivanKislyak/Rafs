from django.db import models
from movies.models import Movie
from parler.models import TranslatableModel, TranslatedFields
from django.utils.translation import gettext_lazy as _

class HomepageCollection(TranslatableModel):
    translations = TranslatedFields(
        title = models.CharField(
            verbose_name=_("Title of Homepage Collection"),
            max_length=200
        )
    )
    is_published = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ['position', 'pk']
        verbose_name = _('Homepage Collection')
        verbose_name_plural = _('Homepage Collections')

    def __str__(self):
        return str(self.safe_translation_getter(
            'title',
            default=self.position,
            any_language=True
        )) or str(self.position)
            

class HomepageCollectionItem(models.Model):
    collection = models.ForeignKey(
        HomepageCollection,
        on_delete=models.CASCADE,
        related_name='items'
    )
    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE,
        related_name='homepage_item'
    )
    position = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['collection', 'movie'], 
                                    name="unique_movie_for_collection"),
            ]
        ordering = ['position', 'pk']
        verbose_name = _('Homepage Collection Item')
        verbose_name_plural = _('Homepage Collection Items')

    def __str__(self):
        return str(
            self.movie.safe_translation_getter(
            'wikidata_name',
            default=self.position,
            any_language=True
        )) or str(self.position)
            

    

