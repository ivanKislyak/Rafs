from django import template

from accounts.models import UserAchievement
from accounts.services.achievements import REVIEW_OR_TREAT_CODE


register = template.Library()


@register.inclusion_tag("accounts/_halloween_award.html", takes_context=True)
def halloween_award(context, message):
    """Supply presentation data only for a server-issued award notification."""
    request = context["request"]
    tags = set(message.tags.split())
    achievement = None
    if (request.user.is_authenticated
            and {"halloween-award-earned", REVIEW_OR_TREAT_CODE} <= tags):
        award = UserAchievement.objects.select_related("achievement").filter(
            user=request.user, achievement__code=REVIEW_OR_TREAT_CODE,
        ).first()
        if award:
            achievement = award.achievement
    return {"achievement": achievement, "user": request.user}
