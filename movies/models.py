from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator

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

    rating = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(10)])
    text = models.TextField()
    contains_spoiler = models.BooleanField(blank=True, default=False)
    likes = models.PositiveSmallIntegerField(default=0, verbose_name="Number of likes")
    dislikes = models.PositiveSmallIntegerField(default=0, verbose_name="Number of dislikes")
    created_at = models.DateField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-likes', 'created_at']
        constraints = [models.UniqueConstraint(fields=['user', 'movie'], name="unique_user_moview_review")]

    def __str__(self):
        if self.text:
            return f"{self.user.username}: {self.text}"
        return f"Review by {self.user.username}"
