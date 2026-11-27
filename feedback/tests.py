from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from .models import Feedback, FeedbackKind
from .tasks import send_feedback_email

URL = reverse("feedback:feedback_api")
MESSAGE = "The search page shows no posters."


class FeedbackAPITests(TestCase):
    def setUp(self):
        # The scoped throttle counts requests in the cache, which outlives each test.
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient()

    def post(self, **data):
        return self.client.post(URL, {"kind": "bug", "message": MESSAGE, "page_url": "/movies/", **data}, format="json")

    @patch("feedback.views.send_feedback_email.delay")
    def test_anonymous_with_email_is_saved_and_queued_after_commit(self, delay):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post(email="guest@example.com")
        self.assertEqual(response.status_code, 201, response.data)
        feedback = Feedback.objects.get()
        self.assertEqual((feedback.email, feedback.kind, feedback.user), ("guest@example.com", FeedbackKind.BUG, None))
        delay.assert_called_once_with(feedback.pk)

    @patch("feedback.views.send_feedback_email.delay")
    def test_anonymous_without_email_is_rejected(self, delay):
        response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)
        self.assertFalse(Feedback.objects.exists())
        delay.assert_not_called()

    @patch("feedback.views.send_feedback_email.delay")
    def test_signed_in_user_is_linked_and_their_email_is_used(self, delay):
        user = get_user_model().objects.create_user(username="reader", email="reader@example.com")
        self.client.force_authenticate(user)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post(email="someone-else@example.com")
        self.assertEqual(response.status_code, 201, response.data)
        feedback = Feedback.objects.get()
        self.assertEqual((feedback.user, feedback.email), (user, "reader@example.com"))

    @patch("feedback.views.send_feedback_email.delay")
    def test_short_message_and_unknown_kind_are_rejected(self, delay):
        self.assertEqual(self.post(email="a@example.com", message="short").status_code, 400)
        self.assertEqual(self.post(email="a@example.com", kind="BUG").status_code, 400)
        self.assertFalse(Feedback.objects.exists())

    @patch("feedback.views.send_feedback_email.delay", side_effect=ConnectionError("broker down"))
    def test_broker_outage_keeps_the_record_and_answers_201(self, delay):
        with self.assertLogs("feedback.views", "ERROR"), self.captureOnCommitCallbacks(execute=True):
            response = self.post(email="guest@example.com")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Feedback.objects.exists())

    @patch("feedback.views.send_feedback_email.delay")
    def test_five_requests_per_hour(self, delay):
        statuses = [self.post(email="guest@example.com").status_code for _ in range(6)]
        self.assertEqual(statuses, [201] * 5 + [429])

    def test_get_is_not_allowed(self):
        self.assertEqual(self.client.get(URL).status_code, 405)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", FEEDBACK_EMAIL="team@example.com")
class FeedbackEmailTaskTests(TestCase):
    def test_email_goes_to_the_team_with_reply_to_the_author(self):
        feedback = Feedback.objects.create(kind="idea", message=MESSAGE, email="guest@example.com", page_url="/movies/1/")
        send_feedback_email(feedback.pk)
        [message] = mail.outbox
        self.assertEqual(message.to, ["team@example.com"])
        self.assertEqual(message.reply_to, ["guest@example.com"])
        self.assertEqual(message.subject, f"[RAFS] Idea: {MESSAGE}")
        self.assertTrue(message.body.startswith(MESSAGE + "\n"))
        self.assertIn("From:   guest@example.com (guest)", message.body)
        self.assertIn("Page:   https://rafs.app/movies/1/", message.body)
        self.assertIn(f"Admin:  https://rafs.app/admin/feedback/feedback/{feedback.pk}/change/", message.body)

    def test_multiline_message_gives_a_one_line_subject_and_names_the_user(self):
        user = get_user_model().objects.create_user(username="reader", email="reader@example.com")
        text = "First line\nsecond line " + "x" * 80
        feedback = Feedback.objects.create(kind="bug", message=text, user=user, email=user.email)
        send_feedback_email(feedback.pk)
        [message] = mail.outbox
        self.assertNotIn("\n", message.subject)
        self.assertTrue(message.subject.startswith("[RAFS] Bug: First line second line x"))
        self.assertTrue(message.subject.endswith("…"))
        self.assertIn("From:   reader <reader@example.com>", message.body)
        self.assertIn("Page:   —", message.body)

    def test_no_reply_to_without_an_email(self):
        user = get_user_model().objects.create_user(username="noemail", email="noemail@example.com")
        feedback = Feedback.objects.create(kind="bug", message=MESSAGE, user=user, email="")
        send_feedback_email(feedback.pk)
        self.assertEqual(mail.outbox[0].reply_to, [])

    def test_deleted_record_is_skipped_quietly(self):
        send_feedback_email(999999)
        self.assertEqual(mail.outbox, [])


class FeedbackAdminTests(TestCase):
    def test_changelist_shows_the_columns_and_filters_by_resolved(self):
        admin = get_user_model().objects.create_superuser(username="boss", email="boss@example.com", password="x")
        self.client.force_login(admin)
        Feedback.objects.create(kind="bug", message=MESSAGE, email="guest@example.com")
        response = self.client.get(reverse("admin:feedback_feedback_changelist"), {"is_resolved__exact": "0"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "guest@example.com")
        self.assertContains(response, "is_resolved__exact")

