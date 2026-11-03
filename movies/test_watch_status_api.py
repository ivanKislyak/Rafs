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
        watch_status = saved_statuses.get()
        self.assertEqual(saved_statuses.count(), 1)
        self.assertEqual(watch_status.status, viewed_watch_status)
                
        