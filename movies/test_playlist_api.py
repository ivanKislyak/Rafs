from rest_framework.test import APITestCase
from accounts.models import User
from .models import Playlist, KindChoice
from django.urls import reverse

class PlaylistAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='first_user',
            email='first_user_email@mail.com'
        )
        self.playlist = Playlist.objects.create(
            name="Playlist of first User",
            owner=self.user,
            kind=KindChoice.CUSTOM,
            is_public=True
        )
        self.url = reverse('movies:playlist_api', kwargs={"pl_id": self.playlist.pk})
        self.client.force_authenticate(user=self.user)

    def test_authenticated_user_gets_existing_playlist(self):
        response = self.client.get(self.url)
        expected_response = {
            "id": self.playlist.pk,
            "name": self.playlist.name,
            "kind": self.playlist.kind,
            "owner": self.user.pk,
            "cover": None,
            "is_public": self.playlist.is_public
        }

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected_response)

