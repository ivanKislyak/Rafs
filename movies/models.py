from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal

class Movie(models.Model):
    name = models.CharField(max_length=200) # Night of the Day of the Dawn of the Son of the Bride...
    year = models.PositiveSmallIntegerField()
    rate = models.DecimalField(decimal_places=1, max_digits=3, null=True, blank=True)
    description = models.TextField(blank=True)
    path = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

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

    rating = models.DecimalField(max_digits=3, decimal_places=1)
    avg_rating = models.DecimalField(max_digits=3, decimal_places=1)
    text = models.TextField()
    contains_spoiler = models.BooleanField(blank=True, default=False)
    created_at = models.DateField(auto_now_add=True)
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
            return f"{self.user.username}: {self.text}"
        return f"Review by {self.user.username}"


class ReviewVote(models.Model):
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
    