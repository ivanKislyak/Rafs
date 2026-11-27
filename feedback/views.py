import logging

from django.db import transaction
from django.shortcuts import render
from rest_framework import generics, permissions, throttling

from .serializers import FeedbackSerializer
from .tasks import send_feedback_email

logger = logging.getLogger(__name__)


def queue_feedback_email(feedback_id):
    """The record is already saved: a broker outage must not turn the answer into a 500."""
    try:
        send_feedback_email.delay(feedback_id)
    except Exception:
        logger.exception("Could not queue the feedback email for %s", feedback_id)


def feedback_page(request):
    # page_url: only a local path from ?from=, never an outside or protocol-relative URL.
    source = request.GET.get("from", "")
    page_url = source[:500] if source.startswith("/") and not source.startswith("//") else ""
    return render(request, "feedback/feedback.html", {"page_url": page_url})


class FeedbackCreateAPIView(generics.CreateAPIView):
    serializer_class = FeedbackSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [throttling.ScopedRateThrottle]
    throttle_scope = "feedback"

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_authenticated:
            feedback_record = serializer.save(user=user, email=user.email)
        else:
            feedback_record = serializer.save()
        transaction.on_commit(lambda: queue_feedback_email(feedback_record.pk))
