from django.db.models.signals import post_save
from django.dispatch import receiver

from movies.models import ReviewReply
from .models import Notification

@receiver(post_save, sender=ReviewReply, dispatch_uid="review_reply_send_notification")
def send_notification_for_review_reply(sender, instance, created, raw=False, **kwargs):
    if not created or raw:
        return

    if instance.user_id == instance.review.user_id:
        return

    Notification.objects.create(
        recipient=instance.review.user,
        kind=Notification.Kind.REPLY,
        actor=instance.user,
        review=instance.review
    )
