from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.urls import reverse
from django.utils import timezone
from django.utils.text import Truncator

from core.seo import PUBLIC_ORIGIN

from .models import Feedback


def feedback_email_body(feedback):
    """The message itself, then a labelled block with full links, so the team sees where it came from."""
    if feedback.user:
        author = feedback.user.username + (f" <{feedback.email}>" if feedback.email else "")
    else:
        author = f"{feedback.email} (guest)"
    details = {
        "Type": feedback.get_kind_display(),
        "From": author,
        "Page": PUBLIC_ORIGIN + feedback.page_url if feedback.page_url else "—",
        "Sent": timezone.localtime(feedback.created_at).strftime("%d.%m.%Y %H:%M"),
        "Admin": PUBLIC_ORIGIN + reverse("admin:feedback_feedback_change", args=[feedback.pk]),
    }
    width = max(map(len, details)) + 1
    lines = [f"{(label + ':').ljust(width)}  {value}" for label, value in details.items()]
    return "\n".join([feedback.message.strip(), "", "—" * 32, *lines])


@shared_task(ignore_result=True)
def send_feedback_email(feedback_id):
    """Email one feedback record to the team; quietly skip a record deleted meanwhile."""
    feedback = Feedback.objects.select_related("user").filter(pk=feedback_id).first()
    if feedback is None:
        return
    EmailMessage(
        # One line: a newline in a header raises BadHeaderError.
        subject=f"[RAFS] {feedback.get_kind_display()}: {Truncator(' '.join(feedback.message.split())).chars(60)}",
        body=feedback_email_body(feedback),
        to=[settings.FEEDBACK_EMAIL],
        reply_to=[feedback.email] if feedback.email else None,
    ).send()
