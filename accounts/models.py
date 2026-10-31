import math
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.utils.translation import gettext_lazy as _
from movies.models import Movie
from django.conf import settings
from django.utils import timezone
from django.conf import settings

class Achievement(models.Model):
    name = models.CharField(max_length=50, verbose_name=_("Name"))
    description = models.CharField(max_length=500, verbose_name=_("Description"))
    badge_image = models.ImageField(upload_to="achievements/", blank=True, null=True, verbose_name=_("Avatar"))
    display_in_profile = models.BooleanField(default=True, verbose_name=_("Display in profile"))
    code = models.SlugField(max_length=80, unique=True, blank=True, null=True, verbose_name=_("Code"))
    starts_at = models.DateTimeField(blank=True, null=True, verbose_name=_("Starts at"))
    ends_at = models.DateTimeField(blank=True, null=True, verbose_name=_("Ends at"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    
    class Meta:
        verbose_name = _("Achievement")
        verbose_name_plural = _("Achievements")

    def __str__(self):
        return self.name

class User(AbstractUser):
    about = models.TextField(blank=True, max_length=1000, verbose_name=_("About me"))
    user_lvl = models.IntegerField(default=1, validators=[MinValueValidator(1)], verbose_name=_("Level"))
    user_frames = models.IntegerField(default=1, validators=[MinValueValidator(1)], verbose_name=_("Frames"))
    email = models.EmailField(_("email address"), unique=True, max_length=256)
    avatar_image = models.ImageField(upload_to="users/avatars/", blank=True, null=True, verbose_name=_("Avatar"))
    is_deleted = models.BooleanField(default=False, verbose_name=_("Deleted"))
    achievement = models.ManyToManyField(
        Achievement,
        blank=True,
        related_name="users", verbose_name=_("Achievements")
    )
    movies = models.ManyToManyField(
        Movie,
        blank=True,
        related_name="users", verbose_name=_("Movies")
    )

    class SexChoice(models.TextChoices):
        MALE = 'M', _("Male")
        FEMALE = 'F', _("Female")
        OTHER = 'O', _("Other")

    sex = models.CharField(max_length=1, choices=SexChoice.choices, null=False, blank=True, default='', verbose_name=_("Sex"))
    country_code = models.CharField(
        max_length=2,
        blank=True,
        default="", verbose_name=_("Country code"),
    )
    bd_date = models.DateField(null=True, blank=True, verbose_name=_("Date of birth"))

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.is_active = False
        self.save()

    def save(self, *args, **kwargs):
        if self.user_frames <= 0:
            self.user_lvl = 1
        else:
            calculated_lvl = int(0.1 * math.sqrt(self.user_frames))
            self.user_lvl = max(1, calculated_lvl)

        if "update_fields" in kwargs and kwargs["update_fields"] is not None:
            update_fields = set(kwargs["update_fields"])
            update_fields.add("user_lvl")
            kwargs["update_fields"] = list(update_fields)

        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")

    def __str__(self):
        return _("%(username)s (%(email)s): Frames: %(frames)s, level: %(level)s") % {
            "username": self.username, "email": self.email,
            "frames": self.user_frames, "level": self.user_lvl,
        }

class UserAchievement(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="achievement_awards", verbose_name=_("User"),
    )
    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.CASCADE,
        related_name="awards", verbose_name=_("Achievement"),
    )
    earned_at = models.DateTimeField(
        default=timezone.now,
        blank=True,
        null=True,
        editable=False, verbose_name=_("Earned at"),
    )
    source_review = models.ForeignKey(
        "movies.Review",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="achievement_awards", verbose_name=_("Source review"),
    )

    class Meta:
        verbose_name = _("User achievement")
        verbose_name_plural = _("User achievements")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "achievement"],
                name="unique_user_achievement",
            ),
        ]

    def __str__(self):
        return f"{self.user_id}: {self.achievement.name}"

class SearchHistory(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="search_history", verbose_name=_("User"),
    )
    query = models.CharField(max_length=200, verbose_name=_("Query"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated at"))

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = _("Search History")
        verbose_name_plural = _("Search Histories")

    def __str__(self):
        return self.query
    
