from django.contrib.auth import get_user_model
from django.test import TestCase

from movies.models import Movie, Review, ReviewReply

from .models import Notification


class NotificationFixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.author = User.objects.create_user(username="author", email="author@example.com")
        cls.replier = User.objects.create_user(username="replier", email="replier@example.com")
        cls.movie = Movie.objects.create(name="Notified movie", year=2024)
        cls.review = Review.objects.create(user=cls.author, movie=cls.movie, rating=8, text="A review")


class ReplyNotificationTests(NotificationFixtures):
    def test_reply_notifies_the_review_author(self):
        ReviewReply.objects.create(review=self.review, user=self.replier, text="I disagree")
        notification = Notification.objects.get()
        self.assertEqual(
            (notification.recipient, notification.kind, notification.actor, notification.review, notification.is_read),
            (self.author, Notification.Kind.REPLY, self.replier, self.review, False),
        )

    def test_own_reply_and_edits_notify_nobody(self):
        own = ReviewReply.objects.create(review=self.review, user=self.author, text="Thanks all")
        own.text = "Edited"
        own.save()
        self.assertFalse(Notification.objects.exists())

    def test_editing_a_reply_does_not_notify_again(self):
        reply = ReviewReply.objects.create(review=self.review, user=self.replier, text="First")
        reply.text = "Second"
        reply.save()
        self.assertEqual(Notification.objects.count(), 1)

