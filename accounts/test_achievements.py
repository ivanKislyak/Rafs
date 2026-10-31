"""Review or Treat uses only isolated test data, never a seeded real event."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as dt_timezone
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.core.cache import cache
from django.db import close_old_connections, connection, transaction
from django.template import Context, Template
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse
from django.contrib.messages.storage.base import Message
from django.contrib.messages import SUCCESS

from accounts.models import Achievement, User, UserAchievement
from accounts.services.achievements import REVIEW_OR_TREAT_CODE, award_review_or_treat
from movies.models import Movie, Review


UTC5 = dt_timezone(timedelta(hours=5))
START = datetime(2026, 10, 31, tzinfo=UTC5)
END = datetime(2026, 11, 4, tzinfo=UTC5)
DURING = START + timedelta(hours=12)


def event(**kwargs):
    return Achievement.objects.create(
        code=REVIEW_OR_TREAT_CODE, name="Review or Treat",
        description='A real badge <description> & details',
        starts_at=START, ends_at=END, **kwargs,
    )


class ReviewOrTreatServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="award-user", email="award@example.com")
        self.movie = Movie.objects.create(name="Any catalogue work")
        self.review = Review.objects.create(user=self.user, movie=self.movie, text="A")
        self.achievement = event()

    def award(self, previous="", now=DURING):
        return award_review_or_treat(self.review, previous, now=now)

    def test_new_review_records_server_time_author_and_source(self):
        award, created = self.award()
        self.assertTrue(created)
        self.assertEqual(award.user, self.review.user)
        self.assertEqual(award.earned_at, DURING)
        self.assertEqual(award.source_review, self.review)

    def test_short_text_and_whitespace_previous_text_qualify(self):
        self.assertTrue(self.award(previous=" \t\n")[1])

    def test_empty_and_whitespace_text_do_not_qualify(self):
        for text in ("", " ", "\n\t "):
            with self.subTest(text=text):
                self.review.text = text
                self.assertEqual(self.award(), (None, False))
        self.assertFalse(UserAchievement.objects.exists())

    def test_nonempty_previous_text_never_qualifies(self):
        for previous in ("A", "Older written review"):
            self.assertEqual(self.award(previous), (None, False))
        self.assertFalse(UserAchievement.objects.exists())

    def test_repeat_preserves_original_time_and_source_even_after_deletion(self):
        first, _ = self.award()
        other = Review.objects.create(user=self.user, movie=Movie.objects.create(name="Other"), text="New text")
        second, created = award_review_or_treat(other, "", now=DURING + timedelta(hours=1))
        self.assertFalse(created)
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(second.earned_at, DURING)
        self.assertEqual(second.source_review, self.review)
        self.review.delete()
        second.refresh_from_db()
        self.assertIsNone(second.source_review)
        self.assertTrue(self.user.achievement.filter(pk=self.achievement.pk).exists())
        self.assertEqual(award_review_or_treat(other, "", now=END), (None, False))
        self.assertEqual(UserAchievement.objects.count(), 1)

    def test_event_boundaries_are_start_inclusive_end_exclusive(self):
        for instant, qualifies in (
            (START - timedelta(microseconds=1), False), (START, True),
            (END - timedelta(seconds=1), True), (END, False),
        ):
            with self.subTest(instant=instant):
                UserAchievement.objects.all().delete()
                self.assertEqual(self.award(now=instant)[1], qualifies)

    def test_missing_and_invalid_event_configuration_is_logged(self):
        for start, end in ((None, END), (START, None), (END, START), (START, START)):
            self.achievement.starts_at, self.achievement.ends_at = start, end
            self.achievement.save()
            with self.assertLogs('accounts.services.achievements', level='WARNING'):
                self.assertEqual(self.award(), (None, False))
        self.achievement.delete()
        with self.assertLogs('accounts.services.achievements', level='WARNING'):
            self.assertEqual(self.award(), (None, False))

    def test_hidden_achievement_is_still_earned_but_not_in_profile_or_count(self):
        self.achievement.display_in_profile = False
        self.achievement.save()
        self.assertTrue(self.award()[1])
        response = self.client.get(reverse('profile', args=[self.user.username]))
        self.assertEqual(response.context['profile_user'].profile_achievements, [])
        self.assertNotContains(response, 'Review or Treat')
        self.assertContains(response, '<span class="profile-section-count">0</span>', html=True)


class ReviewOrTreatFormTests(TransactionTestCase):
    """Real commits let on_commit run before messages middleware saves cookies."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.user = User.objects.create_user(username="event-author", email="event@example.com")
        self.movie = Movie.objects.create(name="A normal non-Halloween work")
        self.achievement = event()
        self.url = reverse('movies:review_form', args=[self.movie.pk])
        self.client.force_login(self.user)
        self.time_patch = patch('accounts.services.achievements.timezone.now', return_value=DURING)
        self.time_patch.start()
        self.addCleanup(self.time_patch.stop)

    def submit(self, text, rating="8.0"):
        return self.client.post(self.url, {'rating': rating, 'text': text})

    def test_new_review_both_rewards_and_notifications_survive_redirect(self):
        response = self.submit('A')
        self.assertRedirects(response, reverse('movies:detail', args=[self.movie.pk]), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual(self.user.user_frames, 101)
        self.assertTrue(self.user.movies.filter(pk=self.movie.pk).exists())
        self.assertEqual(UserAchievement.objects.count(), 1)
        response = self.client.get(response.url)
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 2)
        self.assertTrue(any('frames-reward' in m.tags.split() for m in messages))
        self.assertTrue(any({'success','halloween-award-earned',REVIEW_OR_TREAT_CODE} <= set(m.tags.split()) for m in messages))
        self.assertContains(response, 'data-halloween-award')
        self.assertContains(response, 'data-src="/static/images/halloween/jigsaw_boo.jpg"')
        self.assertNotContains(response, ' src="/static/images/halloween/jigsaw_boo.jpg"')
        self.assertContains(response, 'A real badge &lt;description&gt; &amp; details')
        self.assertContains(response, reverse('profile', args=[self.user.username]))
        again = self.client.get(reverse('profile', args=[self.user.username]))
        self.assertNotContains(again, 'data-halloween-award')
        self.assertContains(again, 'Review or Treat')

    def test_adding_text_to_old_numeric_rating_qualifies_without_more_frames(self):
        review = Review.objects.create(user=self.user, movie=self.movie, text='', rating=5)
        Review.objects.filter(pk=review.pk).update(created_at=START - timedelta(days=100))
        self.submit('New written review')
        award = UserAchievement.objects.get()
        self.assertEqual(award.source_review_id, review.pk)
        self.user.refresh_from_db()
        self.assertEqual(self.user.user_frames, 1)

    def test_other_existing_written_reviews_do_not_disqualify_author(self):
        Review.objects.create(user=self.user, movie=Movie.objects.create(name='Older film'), text='Already wrote before')
        self.submit('Still qualifies')
        self.assertEqual(UserAchievement.objects.count(), 1)

    def test_rating_without_text_still_receives_original_frames_only(self):
        for text in ('', ' \n\t '):
            with self.subTest(text=text):
                self.submit(text)
                self.assertFalse(UserAchievement.objects.exists())
        self.user.refresh_from_db()
        self.assertEqual(self.user.user_frames, 101)

    def test_resaving_or_changing_existing_written_review_never_awards(self):
        Review.objects.create(user=self.user, movie=self.movie, text='Already written')
        self.submit('Already written')
        self.submit('Changed written text')
        self.assertFalse(UserAchievement.objects.exists())

    def test_second_qualifying_review_does_not_notify_or_change_award(self):
        self.submit('First')
        self.client.get(reverse('movies:detail', args=[self.movie.pk]))
        first = UserAchievement.objects.get()
        movie = Movie.objects.create(name='Another work')
        response = self.client.post(reverse('movies:review_form', args=[movie.pk]), {'rating':'7', 'text':'Second'})
        page = self.client.get(response.url)
        self.assertNotContains(page, 'halloween-award-earned')
        self.assertEqual(UserAchievement.objects.count(), 1)
        award = UserAchievement.objects.get()
        self.assertEqual(award.earned_at, first.earned_at)
        self.assertEqual(award.source_review_id, first.source_review_id)

    def test_missing_or_bad_event_does_not_prevent_review_save(self):
        for mode in ('missing', 'invalid'):
            with self.subTest(mode=mode):
                Achievement.objects.filter(code=REVIEW_OR_TREAT_CODE).delete()
                if mode == 'invalid':
                    self.achievement = event()
                    self.achievement.ends_at = START
                    self.achievement.save()
                with self.assertLogs('accounts.services.achievements', level='WARNING'):
                    response = self.submit('Valid review')
                self.assertEqual(response.status_code, 302)
                self.assertTrue(Review.objects.filter(user=self.user, text='Valid review').exists())
                self.assertFalse(UserAchievement.objects.exists())
                Review.objects.all().delete()

    def test_get_anonymous_and_invalid_form_do_not_award(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.submit('Valid text', rating='99').status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {'rating':'8', 'text':'Anonymous'}).status_code, 302)
        self.assertFalse(Review.objects.exists())
        self.assertFalse(UserAchievement.objects.exists())

    def test_transaction_rollback_removes_both_rewards_and_callbacks(self):
        with patch('movies.views.messages.success') as success:
            with self.assertRaisesRegex(RuntimeError, 'rollback'):
                with transaction.atomic():
                    self.client.post(self.url, {'rating':'8', 'text':'Qualifies'})
                    self.assertEqual(UserAchievement.objects.count(), 1)
                    success.assert_not_called()
                    raise RuntimeError('rollback')
            success.assert_not_called()
        self.assertFalse(Review.objects.exists())
        self.assertFalse(UserAchievement.objects.exists())
        self.assertFalse(self.user.movies.exists())
        self.user.refresh_from_db()
        self.assertEqual(self.user.user_frames, 1)

    def test_only_exact_message_tags_and_existing_owned_award_supply_data(self):
        request = RequestFactory().get('/')
        request.user = self.user
        template = Template('{% load achievements %}{% halloween_award message %}')
        def render(tags):
            return template.render(Context({'request':request, 'message':Message(SUCCESS, 'Award', extra_tags=tags)}))
        tags = f'halloween-award-earned {REVIEW_OR_TREAT_CODE}'
        self.assertNotIn('data-halloween-award', render(tags))
        self.submit('A')
        self.assertIn('data-halloween-award', render(tags))
        self.assertNotIn('data-halloween-award', render(f'not-halloween-award-earned {REVIEW_OR_TREAT_CODE}'))
        self.assertNotIn('data-halloween-award', render(f'halloween-award-earned {REVIEW_OR_TREAT_CODE}-fake'))
        self.assertNotIn('data-halloween-award', render('frames-reward'))


@skipUnless(connection.vendor == 'postgresql', 'Real concurrent award checks require isolated PostgreSQL')
class ReviewOrTreatConcurrencyTests(TransactionTestCase):
    def test_concurrent_reviews_create_exactly_one_award(self):
        user = User.objects.create_user(username='concurrent-award', email='concurrent@example.com')
        achievement = event()
        reviews = [Review.objects.create(user=user, movie=Movie.objects.create(name=f'Concurrent {i}'), text='Text') for i in range(2)]
        barrier = Barrier(2)
        def attempt(review_id):
            close_old_connections()
            try:
                review = Review.objects.get(pk=review_id)
                barrier.wait(timeout=10)
                with transaction.atomic():
                    award, created = award_review_or_treat(review, '', now=DURING)
                    return award.pk, created
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, [r.pk for r in reviews]))
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(len({pk for pk, _ in results}), 1)
        self.assertEqual(UserAchievement.objects.filter(user=user, achievement=achievement).count(), 1)
