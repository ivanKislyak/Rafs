from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from movies.models import Movie, Review, ReviewReply

from .context_processors import unread_notifications
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


class NotificationAPITests(NotificationFixtures):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.author)

    def test_addresses_have_a_single_api_prefix(self):
        self.assertEqual(reverse("notifications:list_api"), "/api/v1/notifications/")
        self.assertEqual(reverse("notifications:unread_count_api"), "/api/v1/notifications/unread-count/")
        self.assertEqual(reverse("notifications:mark_read_api"), "/api/v1/notifications/read/")

    def test_guests_are_rejected(self):
        guest = APIClient()
        for name, method in (("list_api", "get"), ("unread_count_api", "get"), ("mark_read_api", "post")):
            with self.subTest(name=name):
                self.assertIn(getattr(guest, method)(reverse(f"notifications:{name}")).status_code, (401, 403))

    def test_list_shows_only_own_notifications_newest_first(self):
        ReviewReply.objects.create(review=self.review, user=self.replier, text="One")
        Notification.objects.create(recipient=self.author, kind=Notification.Kind.FRAMES, amount=100)
        Notification.objects.create(recipient=self.replier, kind=Notification.Kind.FRAMES, amount=5)
        response = self.client.get(reverse("notifications:list_api"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        self.assertEqual((response.data["count"], response.data["next"], response.data["previous"]), (2, None, None))
        self.assertEqual([item["kind"] for item in response.data["results"]], ["frames", "reply"])
        frames, reply = response.data["results"]
        self.assertEqual(
            {key: reply[key] for key in ("actor_username", "review_id", "movie_id", "amount", "is_read")},
            {"actor_username": "replier", "review_id": self.review.id, "movie_id": self.movie.id, "amount": None, "is_read": False},
        )
        self.assertEqual((frames["actor_username"], frames["review_id"], frames["movie_id"], frames["amount"]), (None, None, None, 100))

    def test_deleted_actor_leaves_a_null_username(self):
        ReviewReply.objects.create(review=self.review, user=self.replier, text="One")
        Notification.objects.update(actor=None)
        response = self.client.get(reverse("notifications:list_api"))
        self.assertIsNone(response.data["results"][0]["actor_username"])

    def test_list_is_paged_by_the_project_default(self):
        Notification.objects.bulk_create(
            Notification(recipient=self.author, kind=Notification.Kind.FRAMES, amount=i) for i in range(30)
        )
        url = reverse("notifications:list_api")
        first = self.client.get(url).data
        self.assertEqual((first["count"], len(first["results"]), first["previous"]), (30, 25, None))
        self.assertTrue(first["next"].endswith("/api/v1/notifications/?page=2"))
        second = self.client.get(url, {"page": 2}).data
        self.assertEqual((len(second["results"]), second["next"]), (5, None))
        ids = [item["id"] for item in first["results"] + second["results"]]
        self.assertEqual(len(set(ids)), 30)

    def test_unread_count_and_mark_all_read(self):
        Notification.objects.create(recipient=self.author, kind=Notification.Kind.FRAMES, amount=1)
        Notification.objects.create(recipient=self.author, kind=Notification.Kind.FRAMES, amount=2)
        other = Notification.objects.create(recipient=self.replier, kind=Notification.Kind.FRAMES, amount=3)
        count = reverse("notifications:unread_count_api")
        self.assertEqual(self.client.get(count).data, {"unread": 2})
        self.assertEqual(self.client.post(reverse("notifications:mark_read_api")).status_code, 204)
        self.assertEqual(self.client.get(count).data, {"unread": 0})
        other.refresh_from_db()
        self.assertFalse(other.is_read)

    def test_mark_read_is_post_only(self):
        self.assertEqual(self.client.get(reverse("notifications:mark_read_api")).status_code, 405)


class UnreadContextProcessorTests(NotificationFixtures):
    def test_counts_unread_for_the_signed_in_user_and_zero_for_guests(self):
        from django.contrib.auth.models import AnonymousUser

        Notification.objects.create(recipient=self.author, kind=Notification.Kind.FRAMES, amount=1)
        Notification.objects.create(recipient=self.author, kind=Notification.Kind.FRAMES, amount=1, is_read=True)
        request = RequestFactory().get("/")
        request.user = self.author
        self.assertEqual(unread_notifications(request), {"unread_notifications_count": 1})
        request.user = AnonymousUser()
        self.assertEqual(unread_notifications(request), {"unread_notifications_count": 0})
