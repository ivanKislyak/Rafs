from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinLengthValidator


class FeedbackKind(models.TextChoices):
    BUG = "bug", _("Bug")
    IDEA = "idea", _("Idea")
    OTHER = "other", _("Other")

class Feedback(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="feedbacks",
        verbose_name=_("User"),
        blank=True,
        null=True,
    )
    email = models.EmailField(
        blank=True,
        verbose_name=_("Email"),
    )
    kind = models.CharField(
        max_length=10, 
        choices=FeedbackKind.choices,
        default=FeedbackKind.BUG,
        verbose_name=_("Feedback Kind"))
    message = models.TextField(
        validators=[MinLengthValidator(10, message=_("At least 10 characters"))],
        verbose_name=_("Message"))
    page_url = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("Page URL")
    )
    is_resolved = models.BooleanField(
        default=False,
        verbose_name=_("Resolved")
    )
    created_at = models.DateTimeField(
        auto_now_add=True, 
        verbose_name=_("Created at")
    )

    class Meta:
        verbose_name = _("Feedback")
        verbose_name_plural = _("Feedbacks")
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False)
                    | ~models.Q(email="")
                ),
                name="feedback_user_or_email"
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} from {self.user.username if self.user else self.email or 'anonymous'}"
    
