from django.db import transaction
from django.db.models import F

from accounts.models import User
from notifications.models import Notification


def award_frames(user, amount):
    """Add frames under a row lock and notify the user, plus a level-up notification when the level grows."""
    if amount <= 0:
        raise ValueError("The number of frames must be positive")

    with transaction.atomic():
        user_lvl = User.objects.select_for_update().get(pk=user.pk).user_lvl
        User.objects.filter(pk=user.pk).update(user_frames=F("user_frames") + amount)
        user.refresh_from_db()
        user.save()  # User.save() recalculates user_lvl from the new frames.

        Notification.objects.create(recipient=user, kind=Notification.Kind.FRAMES, amount=amount)
        if user_lvl != user.user_lvl:
            Notification.objects.create(recipient=user, kind=Notification.Kind.LEVEL_UP, amount=user.user_lvl)
    return user
