from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

class Notification(models.Model):
    class Kind(models.TextChoices):
        REPLY = "reply", _("Reply")
        FRAMES = "frames", _("Frames")
        LEVEL_UP = "level_up", _("Level Up")

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("Recipient"),
    )
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        verbose_name=_("Kind"),
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
        verbose_name=_("Actor"),
    )
    review = models.ForeignKey(
        'movies.Review',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        verbose_name=_("Review"),
    )
    amount = models.IntegerField(
        null=True,
        blank=True,
        verbose_name=_("Amount"),
    )
    is_read = models.BooleanField(default=False, verbose_name=_("Read"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created at"))

    class Meta:
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")
        ordering = ['-created_at', '-pk']
        indexes = [
            models.Index(fields=['recipient', '-created_at']),
        ]
