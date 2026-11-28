from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.services.frames import award_frames
from notifications.models import Notification


class AwardFramesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="earner", email="earner@example.com")

    def test_frames_are_added_with_a_frames_notification(self):
        award_frames(self.user, 50)
        self.user.refresh_from_db()
        self.assertEqual((self.user.user_frames, self.user.user_lvl), (51, 1))
        notification = Notification.objects.get()
        self.assertEqual((notification.recipient, notification.kind, notification.amount), (self.user, "frames", 50))

    def test_level_up_adds_a_second_notification_with_the_new_level(self):
        # Level is int(0.1 * sqrt(frames)): 1 + 899 = 900 frames is level 3.
        award_frames(self.user, 899)
        self.assertEqual(self.user.user_lvl, 3)
        kinds = sorted(Notification.objects.values_list("kind", "amount"))
        self.assertEqual(kinds, [("frames", 899), ("level_up", 3)])

    def test_the_passed_object_and_the_database_agree(self):
        stale = get_user_model().objects.get(pk=self.user.pk)
        award_frames(self.user, 10)
        award_frames(stale, 10)
        self.user.refresh_from_db()
        self.assertEqual(self.user.user_frames, 21)

    def test_zero_or_negative_amount_is_rejected(self):
        for amount in (0, -5):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                award_frames(self.user, amount)
        self.assertFalse(Notification.objects.exists())
