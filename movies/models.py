from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from django.db.models import Avg
from taggit.managers import TaggableManager
from .movie_models import TypeOfWork, Genre, Country, Studio, Person
from parler.models import TranslatableModel, TranslatedFields
from django.contrib.postgres.indexes import GinIndex
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.postgres.search import SearchVectorField
from django.utils.translation import gettext_lazy as _


class Movie(TranslatableModel):
    # Main data
    wikidata_id = models.CharField(verbose_name=_("ID on wikidata.org"), max_length=20, unique=True, null=True, blank=True)
    imdb_id = models.CharField(verbose_name=_("ID on imdb.com"), max_length=20, null=True, blank=True, db_index=True)

    translations = TranslatedFields(
        wikidata_name = models.CharField(verbose_name=_("Movie Name"), max_length=500, blank=True),
        wikidata_description = models.TextField(verbose_name=_("Movie Description"), blank=True)
    )

    year = models.PositiveSmallIntegerField(verbose_name=_("Year of Release"), null=True, blank=True)
    type_of_work = models.ForeignKey(
        TypeOfWork, 
        on_delete=models.SET_NULL, 
        blank=True,
        null=True, 
        related_name="movies",
        verbose_name=_("Type of Work"))

    genres = models.ManyToManyField(Genre, blank=True, related_name="movies", verbose_name=_("Genres"))
    countries = models.ManyToManyField(Country, blank=True, related_name="movies", verbose_name=_("Countries"))
    studio = models.ManyToManyField(Studio, blank=True, related_name="movies", verbose_name=_("Studios"))

    # Persons
    director = models.ManyToManyField(Person, blank=True, related_name="directed_movies", verbose_name=_("Directors"))
    screenwriter = models.ManyToManyField(Person, blank=True, related_name="written_movies", verbose_name=_("Screenwriters"))
    producer = models.ManyToManyField(Person, blank=True, related_name="produced_movies", verbose_name=_("Producers"))
    composer = models.ManyToManyField(Person, blank=True, related_name="composed_movies", verbose_name=_("Composers"))
    actors = models.ManyToManyField(Person, blank=True, related_name="acted_in_movies", verbose_name=_("Actors"))

    cover_url = models.URLField(blank=True, verbose_name=_("Cover URL"))
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Last synced at"))

    name = models.CharField(max_length=200, blank=True, verbose_name=_("Name")) # Night of the Day of the Dawn of the Son of the Bride...
    rate = models.DecimalField(decimal_places=1, max_digits=3, null=True, blank=True, verbose_name=_("Rating"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    tags = TaggableManager(blank=True)
    cover = models.ImageField(upload_to="movie_covers/", blank=True, null=True, verbose_name=_("Cover"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    @property
    def avg_rating(self):
        raw_avg_rating = getattr(self, "review_avg_rating", None)
        if raw_avg_rating is None and not hasattr(self, "review_avg_rating"):
            raw_avg_rating = self.reviews.aggregate(Avg("avg_rating"))["avg_rating__avg"]
        return round(raw_avg_rating, 1) if raw_avg_rating is not None else 0.0

    @property
    def image_exists(self):
        return bool(self.cover and self.cover.storage.exists(self.cover.name))

    class Meta:
        ordering = ['-rate', 'name']
        verbose_name = _("Movie")
        verbose_name_plural = _("Movies")

    def __str__(self):
        if self.year:
            return f"{self.name} ({self.year})"
        else:
            return self.name


class AnimationImportReceipt(models.Model):
    """Commit provenance with Movie; SQLite progress can then be recovered safely."""

    campaign = models.UUIDField()
    media_type = models.CharField(max_length=5, choices=[("movie", "movie"), ("tv", "tv")])
    tmdb_id = models.PositiveBigIntegerField()
    wikidata_id = models.CharField(max_length=20)
    movie = models.ForeignKey(Movie, on_delete=models.SET_NULL, null=True)
    outcome = models.CharField(max_length=8, choices=[(x, x) for x in ("created", "updated", "existing")])
    indexed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["campaign", "media_type", "tmdb_id"], name="unique_animation_receipt")]
        indexes = [models.Index(fields=["campaign", "outcome"], name="animation_campaign_outcome")]


class Review(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,                       
        related_name="reviews", verbose_name=_("User"))

    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE, 
        related_name="reviews", verbose_name=_("Movie"))
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=5.0, validators=[MinValueValidator(0), MaxValueValidator(10)], verbose_name=_("Rating"))
    avg_rating = models.DecimalField(max_digits=3, decimal_places=1, default=5.0, validators=[MinValueValidator(0), MaxValueValidator(10)], blank=True, null=True, verbose_name=_("Average rating"))
    idea_rating = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(10)], blank=True, null=True, verbose_name=_("Idea rating"))
    execution_rating = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(10)], blank=True, null=True, verbose_name=_("Execution rating"))
    characters_rating = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(10)], blank=True, null=True, verbose_name=_("Characters rating"))
    sound_rating = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(10)], blank=True, null=True, verbose_name=_("Sound rating"))
    text = models.TextField(blank=True, verbose_name=_("Review text"))
    contains_spoiler = models.BooleanField(blank=True, default=False, verbose_name=_("Contains spoilers"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    def save(self, *args, **kwargs):
        rating_sides = [self.rating]
    
        if self.idea_rating is not None: rating_sides.append(self.idea_rating)
        if self.execution_rating is not None: rating_sides.append(self.execution_rating)
        if self.characters_rating is not None: rating_sides.append(self.characters_rating)
        if self.sound_rating is not None: rating_sides.append(self.sound_rating)
        
        self.avg_rating = round(sum(rating_sides) / len(rating_sides), 1)
        super().save(*args, **kwargs)


    class Meta:
        verbose_name = _("Review")
        verbose_name_plural = _("Reviews")
        ordering = ['-created_at', '-pk']
        constraints = [
            models.UniqueConstraint(fields=['user', 'movie'], 
                                    name="unique_user_moview_review"),
            models.CheckConstraint(
                condition=(
                    models.Q(rating__gte=Decimal("0.0"))
                    & models.Q(rating__lte=Decimal("10.0"))
                ),
                name="rating_between_0_and_10"
                )]

    def __str__(self):
        if self.text:
            return _("Review by %(username)s for %(movie)s (%(rating)s): %(text)s") % {
                "username": self.user.username, "movie": self.movie.name,
                "rating": self.avg_rating, "text": self.text,
            }
        return _("Rating for %(movie)s by %(username)s: %(rating)s") % {
            "movie": self.movie.name, "username": self.user.username, "rating": self.avg_rating,
        }

class ReviewReply(models.Model):
    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name="replies", verbose_name=_("Review") # For review.replies.count()
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_replies", verbose_name=_("User")
    )
    text = models.TextField(verbose_name=_("Reply text"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        verbose_name = _("Review Reply")
        verbose_name_plural = _("Review Replies")
        ordering = ['created_at']

    def __str__(self):
        return _("Reply from %(username)s to review #%(review_id)s") % {
            "username": self.user.username, "review_id": self.review.id,
        }

class BaseVote(models.Model):
    """An abstract class for likes and dislikes"""
    class VoteChoice(models.IntegerChoices):
        LIKE = 1, "Like"
        DISLIKE = -1, "Dislike"

    value = models.SmallIntegerField(choices=VoteChoice.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class ReviewVote(BaseVote):
    """Likes and dislikes on reviews."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_votes")
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="votes")

    class Meta:
        verbose_name = _("Review Vote")
        verbose_name_plural = _("Review Votes")
        constraints = [models.UniqueConstraint(fields=["user", "review"], name="unique_user_review_vote")]


class ReplyVote(BaseVote):
    """Likes and dislikes on review replies."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reply_votes")
    reply = models.ForeignKey(ReviewReply, on_delete=models.CASCADE, related_name="votes")

    class Meta:
        verbose_name = _("Reply Vote")
        verbose_name_plural = _("Reply Votes")
        constraints = [models.UniqueConstraint(fields=["user", "reply"], name="unique_user_reply_vote")]


class GlobalSearchIndex(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    search_vector = SearchVectorField(null=True)
   
    class Meta:
        verbose_name = _("Global Search Index")
        verbose_name_plural = _("Global Search Indexes")
        indexes = [
            GinIndex(fields=['search_vector']),
        ]
        constraints = [
            models.UniqueConstraint(fields=["content_type", "object_id"], name="unique_gsi_target"),
        ]

    def __str__(self):
        return f"{self.content_type.model} #{self.object_id} and query - {self.content_object}"
 

class WatchStatus(models.Model):
    class StatusChoice(models.TextChoices):
        WILL_WATCH = "WILL_WATCH", _("I'll watch it")
        VIEWED = "VIEWED", _("Viewed")
        NOT_INTERESTING = "NOT_INTERESTING", _("I'm not interested")
        WATCHING = "WATCHING", _("I'm watching it right now")    
        DROPPED = "DROPPED", _("I dropped watching it")
        REWATCHING = "REWATCHING", _("Rewatching")

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="watch_statuses", verbose_name=_("User"))
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name="watch_statuses", verbose_name=_("Movie"))
    status = models.CharField(max_length=20, choices=StatusChoice.choices, default=StatusChoice.VIEWED, verbose_name=_("Status"))

    class Meta:
        verbose_name = _("Watch Status")
        verbose_name_plural = _("Watch Statuses")
        constraints = [models.UniqueConstraint(fields=["user", "movie"], name="unique_movie_status")]

    def __str__(self):
        return self.get_status_display()