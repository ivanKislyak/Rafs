from rest_framework.test import APITestCase
from accounts.models import User
from .models import Movie, WatchStatus
from django.urls import reverse

class WatchStatusWriteAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username = "watch-status-api-test",
            email="watch-status-api-test@example.com"
        )
        self.movie = Movie.objects.create(
            name ='Harry Potter',
            year = 2001
        )
        self.url = reverse('movies:watch_status_api', kwargs={"movie_id": self.movie.pk})
        self.client.force_authenticate(user=self.user) # type: ignore

    def test_put_creates_watch_status(self):
        viewed_watch_status = WatchStatus.StatusChoice.VIEWED
        response = self.client.put(
            self.url,
            {"status": viewed_watch_status},
            format="json",
        )
        should_be_response = {
            "movie_id": self.movie.pk,
            "status": viewed_watch_status
        }
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), should_be_response)

        saved_statuses = WatchStatus.objects.filter(
            user=self.user, 
            movie=self.movie.pk
        )
        self.assertEqual(saved_statuses.count(), 1)
        watch_status = saved_statuses.get()
        self.assertEqual(watch_status.status, viewed_watch_status)
                
    def test_put_updates_existing_watch_status_without_duplicate(self):
        will_watch_status = WatchStatus.StatusChoice.WILL_WATCH
        viewed_watch_status = WatchStatus.StatusChoice.VIEWED
        first_status = WatchStatus.objects.create(
            user=self.user,
            movie=self.movie,
            status=will_watch_status
        )
        first_status_id = first_status.pk

        response = self.client.put(
            self.url,
            {"status": viewed_watch_status},
            format="json",
        )
        expected_json = {
            "movie_id": self.movie.pk,
            "status": viewed_watch_status
        }

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected_json)
        first_status.refresh_from_db()
        self.assertEqual(first_status.status, viewed_watch_status)
        saved_statuses = WatchStatus.objects.filter(
            user=self.user,
            movie=self.movie.pk
        )
        self.assertEqual(saved_statuses.count(), 1)
        self.assertEqual(saved_statuses.get().pk, first_status_id)

    def test_put_invalid_status_keeps_saved_status_unchanged(self):
        watching_status = WatchStatus.StatusChoice.WATCHING
        existing_status = WatchStatus.objects.create(
            user=self.user,
            movie=self.movie,
            status=watching_status
        )

        response = self.client.put(
            self.url,
            {"status": "INVALID_STATUS"}, 
            format="json"
        )
        self.assertEqual(response.status_code, 400)
        existing_status.refresh_from_db()
        saved_statuses = WatchStatus.objects.filter(
            user=self.user,
            movie=self.movie,
        )
        self.assertEqual(saved_statuses.count(), 1)
        self.assertEqual(existing_status.status, watching_status)

    def test_anonymous_put_does_not_create_watch_status(self):
        self.client.force_authenticate(user=None)
        viewed_watch_status = WatchStatus.StatusChoice.VIEWED
        
        response = self.client.put(
            self.url,
            {"status": viewed_watch_status}, 
            format="json"
        )
        self.assertEqual(response.status_code, 403)
        saved_statuses = WatchStatus.objects.filter(
            user=self.user,
            movie=self.movie,
        )
        self.assertEqual(saved_statuses.count(), 0)
    
    def test_delete_removes_only_current_users_watch_status(self):
        viewed_watch_status = WatchStatus.StatusChoice.VIEWED
        dropped_status = WatchStatus.StatusChoice.DROPPED
        
        WatchStatus.objects.create(
            user=self.user,
            movie=self.movie,
            status=viewed_watch_status
        )
        alien = User.objects.create_user(
            username='alien',
            email='alien-test@gmail.com'
        )
        WatchStatus.objects.create(
            user=alien,
            movie=self.movie,
            status=dropped_status
        )
        response = self.client.delete(self.url)
        
        self.assertEqual(response.status_code, 204)
        user_record_watch_status = WatchStatus.objects.filter(
            user=self.user,
            movie=self.movie,
        )
        self.assertEqual(user_record_watch_status.count(), 0)
        alien_record_watch_status = WatchStatus.objects.filter(
            user=alien,
            movie=self.movie,
        )
        self.assertEqual(alien_record_watch_status.get().status, dropped_status)
