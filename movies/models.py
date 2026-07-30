from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
from django.db.models import Avg

class Movie(models.Model):
    name = models.CharField(max_length=200) # Night of the Day of the Dawn of the Son of the Bride...
    year = models.PositiveSmallIntegerField()
    rate = models.DecimalField(decimal_places=1, max_digits=3, null=True, blank=True)
    description = models.TextField(blank=True)
    path = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def avg_rating(self):
        raw_avg_rating = self.reviews.aggregate(Avg("rating"))["rating__avg"]
        return round(raw_avg_rating, 1) if raw_avg_rating is not None else 0.0
    
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
    text = models.TextField(blank=True)
    contains_spoiler = models.BooleanField(blank=True, default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
            return f"{self.user.username} оставил отзыв к фильму - {self.movie.name}: {self.text}"
        return f"{self.movie.name} was review by {self.user.username}"


class ReviewVote(models.Model):
    """Лайки/Дизлайки к отзывам"""
    class VoteChoice(models.IntegerChoices):
       LIKE = 1, "Like"
       DISLIKE = -1, "Dislike"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,                       
        related_name="review_votes"
    )
    review = models.ForeignKey(
       Review,
       on_delete=models.CASCADE,                       
       related_name="votes"
    )
    value = models.SmallIntegerField(choices=VoteChoice.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "review"], name="unique_user_review_vote"
            )
        ]
    