from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from django.db.models import Avg
from taggit.managers import TaggableManager
from .movie_models import TypeOfWork, Genre, Country, Studio, Person
from parler.models import TranslatableModel, TranslatedFields

class Movie(TranslatableModel):
    # Main data
    wikidata_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    imdb_id = models.CharField(max_length=20, null=True, blank=True, db_index=True)

    translations = TranslatedFields(
        wikidata_name = models.CharField(max_length=200, blank=True),
        wikidata_description = models.TextField(blank=True)
    )

    year = models.PositiveSmallIntegerField(null=True, blank=True)

    type_of_work = models.ForeignKey(
        TypeOfWork, 
        on_delete=models.SET_NULL, 
        blank=True,
        null=True, 
        related_name="movies")

    genres = models.ManyToManyField(Genre, blank=True, related_name="movies")
    countries = models.ManyToManyField(Country, blank=True, related_name="movies")
    studio = models.ManyToManyField(Studio, blank=True, related_name="movies")

    # Persons
    director = models.ManyToManyField(Person, blank=True, related_name="directed_movies")
    screenwriter = models.ManyToManyField(Person, blank=True, related_name="written_movies")
    producer = models.ManyToManyField(Person, blank=True, related_name="produced_movies")
    composer = models.ManyToManyField(Person, blank=True, related_name="composed_movies")
    actors = models.ManyToManyField(Person, blank=True, related_name="acted_in_movies")

    cover_url = models.URLField(blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    name = models.CharField(max_length=200, blank=True) # Night of the Day of the Dawn of the Son of the Bride...

    rate = models.DecimalField(decimal_places=1, max_digits=3, null=True, blank=True)
    description = models.TextField(blank=True)
    tags = TaggableManager()
    cover = models.ImageField(upload_to="movie_covers/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

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

    def __str__(self):
        if self.year:
            return f"{self.name}, ({self.year})"
        else:
            return self.name


class Review(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,                       
        related_name="reviews")

    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE, 
        related_name="reviews")
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=5.0, validators=[MinValueValidator(0), MaxValueValidator(10)])
    avg_rating = models.DecimalField(max_digits=3, decimal_places=1, default=5.0, validators=[MinValueValidator(0), MaxValueValidator(10)], blank=True, null=True)
    idea_rating = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(10)], blank=True, null=True)
    execution_rating = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(10)], blank=True, null=True)
    characters_rating = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(10)], blank=True, null=True)
    sound_rating = models.DecimalField(max_digits=3, decimal_places=1, validators=[MinValueValidator(0), MaxValueValidator(10)], blank=True, null=True)
    text = models.TextField(blank=True)
    contains_spoiler = models.BooleanField(blank=True, default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        rating_sides = [self.rating]
    
        if self.idea_rating is not None: rating_sides.append(self.idea_rating)
        if self.execution_rating is not None: rating_sides.append(self.execution_rating)
        if self.characters_rating is not None: rating_sides.append(self.characters_rating)
        if self.sound_rating is not None: rating_sides.append(self.sound_rating)
        
        self.avg_rating = round(sum(rating_sides) / len(rating_sides), 1)
        super().save(*args, **kwargs)


    class Meta:
        ordering = ['-created_at']
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
            return f"{self.user.username} оставил отзыв к фильму {self.movie.name} ({self.avg_rating}): {self.text}"
        return f"{self.movie.name} was review ({self.avg_rating}) by {self.user.username}"

class ReviewReply(models.Model):
    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name="replies" # For review.replies.count()
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_replies"
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Ответ от {self.user.username} к отзыву #{self.review.id}"

class BaseVote(models.Model):
    """Абстрактный класс для лайков/дизлайков"""
    class VoteChoice(models.IntegerChoices):
        LIKE = 1, "Like"
        DISLIKE = -1, "Dislike"

    value = models.SmallIntegerField(choices=VoteChoice.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class ReviewVote(BaseVote):
    """Лайки/Дизлайки к отзывам"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_votes")
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="votes")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "review"], name="unique_user_review_vote")]


class ReplyVote(BaseVote):
    """Лайки/Дизлайки к ответам на отзывы"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reply_votes")
    reply = models.ForeignKey(ReviewReply, on_delete=models.CASCADE, related_name="votes")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "reply"], name="unique_user_reply_vote")]