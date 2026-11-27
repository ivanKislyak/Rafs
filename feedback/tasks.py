from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage

from .models import Feedback


@shared_task(ignore_result=True)
def send_feedback_email(feedback_id):
    """Email one feedback record to the team; quietly skip a record deleted meanwhile."""
    feedback = Feedback.objects.filter(pk=feedback_id).first()
    if feedback is None:
        return
    EmailMessage(
        subject=f"[RAFS] {feedback.get_kind_display()}",
        body=f"{feedback.message}\n\n{feedback.page_url}",
        to=[settings.FEEDBACK_EMAIL],
        reply_to=[feedback.email] if feedback.email else None,
    ).send()
