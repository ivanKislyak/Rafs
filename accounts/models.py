from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    avatar_image = models.ImageField(upload_to="users/avatars/", blank=True, null=True)
    is_deleted = models.BooleanField(default=False)

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.is_active = False
        self.save()
