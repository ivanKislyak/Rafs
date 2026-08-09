import math
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

class User(AbstractUser):
    user_lvl = models.IntegerField(default=1)
    user_frames = models.IntegerField(default=1)
    email = models.EmailField(_("email address"), unique=True, max_length=256)
    avatar_image = models.ImageField(upload_to="users/avatars/", blank=True, null=True)
    is_deleted = models.BooleanField(default=False)

    class SexChoice(models.TextChoices):
        MALE = 'M', _("Male")
        FEMALE = 'F', _("Female")
        OTHER = 'O', _("Other")

    sex = models.CharField(max_length=1, choices=SexChoice.choices, null=False, blank=True, default='')
    bd_date = models.DateField(null=True, blank=True)

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

    def __str__(self):
        return f"{self.username} with email - {self.email} has {self.user_frames} frames and {self.user_lvl} lvl"
