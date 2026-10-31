import logging

from django.utils import timezone

from accounts.models import Achievement, UserAchievement


logger = logging.getLogger(__name__)
REVIEW_OR_TREAT_CODE = "review-or-treat-2026"


def award_review_or_treat(review, previous_text, *, now=None):
    """Award this edition only when a saved rating first acquires review text.

    Call inside the review's transaction. The unique user/achievement constraint
    and get_or_create also protect concurrent attempts on different reviews.
    """
    if (previous_text or "").strip() or not (review.text or "").strip():
        return None, False

    achievement = Achievement.objects.filter(code=REVIEW_OR_TREAT_CODE).first()
    if achievement is None:
        logger.warning("%s: achievement is not configured", REVIEW_OR_TREAT_CODE)
        return None, False
    start, end = achievement.starts_at, achievement.ends_at
    if (start is None or end is None or timezone.is_naive(start)
            or timezone.is_naive(end) or start >= end):
        logger.warning("%s: missing or invalid event dates", REVIEW_OR_TREAT_CODE)
        return None, False

    now = timezone.now() if now is None else now
    if not start <= now < end:
        return None, False

    return UserAchievement.objects.get_or_create(
        user_id=review.user_id,
        achievement=achievement,
        defaults={"earned_at": now, "source_review": review},
    )
