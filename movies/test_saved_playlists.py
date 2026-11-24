"""Tests for saving another user's public playlist to your library.

Covers PUT/DELETE api/v1/playlists/<external_id>/save/ and GET api/v1/library/.
Run with:
    python manage.py test movies.test_saved_playlists
"""
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, reverse
from rest_framework.test import APITestCase

from accounts.models import User
from movies.models import Movie, Playlist, PlaylistItem, SavedPlaylist

EXCHANGES = []


class RecordingMixin:
    longMessage = False

    def api(self, method, url, data=None, label=""):
        call = getattr(self.client, method)
        response = call(url, data, format="json") if data is not None else call(url)
        try:
            body = response.json() if response.content else None
        except ValueError:
            body = response.content.decode()[:300]
        EXCHANGES.append({"label": label or self._testMethodName, "method": method.upper(),
                          "url": url, "request": data, "status": response.status_code, "response": body})
        return response


class SavedPlaylistTests(RecordingMixin, APITestCase):
    def setUp(self):
        self.ivan = User.objects.create_user(username="ivan", email="ivan@rafs.test")
        self.fan = User.objects.create_user(username="kino_fan", email="kino_fan@rafs.test")
        self.public = Playlist.objects.create(owner=self.ivan, name="Carrey marathon", is_public=True)
        self.private = Playlist.objects.create(owner=self.ivan, name="Draft", is_public=False)
        for pos, name in enumerate(["Bruce Almighty", "The Mask", "The Truman Show"], start=1):
            PlaylistItem.objects.create(playlist=self.public, movie=Movie.objects.create(name=name), position=pos)
        self.client.force_authenticate(user=self.fan)

    def save_url(self, playlist):
        try:
            return reverse("movies:playlist_save_api", kwargs={"pl_external_id": playlist.external_id})
        except NoReverseMatch:
            self.fail("Route movies:playlist_save_api not found (api/v1/playlists/<slug:pl_external_id>/save/).")

    def library_url(self):
        try:
            return reverse("movies:library_api")
        except NoReverseMatch:
            self.fail("Route movies:library_api not found (api/v1/library/).")

    def results(self, response):
        data = response.data
        return data["results"] if isinstance(data, dict) and "results" in data else data

    def test_01_save_public_playlist(self):
        """Saving another user's public playlist returns 201 and creates the record"""
        response = self.api("put", self.save_url(self.public), label="success: save")
        self.assertEqual(response.status_code, 201, f"Expected 201, got {response.status_code}: {response.data}")
        self.assertTrue(SavedPlaylist.objects.filter(user=self.fan, playlist=self.public).exists(),
                        "Got 201, but there is no SavedPlaylist in the database.")

    def test_02_save_twice_is_idempotent(self):
        """A repeated PUT returns 200 and there is still a single record"""
        self.client.put(self.save_url(self.public))
        response = self.api("put", self.save_url(self.public), label="success: already saved")
        self.assertEqual(response.status_code, 200,
                         f"Expected 200, got {response.status_code}. "
                         "PUT is idempotent: a repeat means 'already saved', not an error.")
        self.assertEqual(SavedPlaylist.objects.filter(user=self.fan, playlist=self.public).count(), 1)

    def test_03_unsave(self):
        """DELETE returns 204, and a repeated DELETE returns 204 too"""
        self.client.put(self.save_url(self.public))
        response = self.api("delete", self.save_url(self.public), label="success: remove from library")
        self.assertEqual(response.status_code, 204, f"Expected 204, got {response.status_code}.")
        self.assertFalse(SavedPlaylist.objects.exists(), "The record was not deleted.")
        again = self.client.delete(self.save_url(self.public))
        self.assertEqual(again.status_code, 204,
                         f"A repeated DELETE returned {again.status_code}. "
                         "Like DELETE items/<id>/, it should simply return 204.")

    def test_04_cannot_save_own(self):
        """Saving your own playlist is rejected with 400"""
        self.client.force_authenticate(user=self.ivan)
        response = self.api("put", self.save_url(self.public), label="error: own playlist")
        self.assertEqual(response.status_code, 400, f"Expected 400, got {response.status_code}.")
        self.assertFalse(SavedPlaylist.objects.exists())

    def test_05_private_is_not_found(self):
        """Another user's private playlist returns 404 and creates no record"""
        response = self.api("put", self.save_url(self.private), label="error: private playlist")
        self.assertEqual(response.status_code, 404,
                         f"Expected 404, got {response.status_code}. "
                         "To other users a private playlist does not exist.")
        self.assertFalse(SavedPlaylist.objects.exists())

    def test_06_anonymous(self):
        """Anonymous users get 403 both for saving and for the library"""
        self.client.force_authenticate(user=None)
        self.assertEqual(self.api("put", self.save_url(self.public), label="error: anonymous").status_code, 403)
        self.assertEqual(self.client.get(self.library_url()).status_code, 403,
                         "The library must not be available to anonymous users.")

    def test_07_unique_constraint(self):
        """The model enforces uniqueness of (user, playlist)"""
        SavedPlaylist.objects.create(user=self.fan, playlist=self.public)
        with self.assertRaises(IntegrityError, msg="A duplicate record was created. A UniqueConstraint is required."):
            with transaction.atomic():
                SavedPlaylist.objects.create(user=self.fan, playlist=self.public)

    def test_08_library_list(self):
        """The library lists only my saved playlists, newest first, with the expected fields"""
        second = Playlist.objects.create(owner=self.ivan, name="Cartoons", is_public=True)
        self.client.put(self.save_url(self.public))
        self.client.put(self.save_url(second))
        other = User.objects.create_user(username="other", email="other@rafs.test")
        SavedPlaylist.objects.create(user=other, playlist=self.public)
        response = self.api("get", self.library_url(), label="library")
        self.assertEqual(response.status_code, 200, f"Expected 200, got {response.status_code}.")
        rows = self.results(response)
        self.assertEqual([r.get("id") for r in rows], [second.external_id, self.public.external_id],
                         "Expected only the current user's saved playlists, newest first, "
                         "with id equal to the playlist's external_id.")
        expected = {"id", "name", "owner_username", "movies_count", "saved_at"}
        missing = expected - set(rows[0])
        self.assertFalse(missing, f"Missing fields in the item: {sorted(missing)}.")
        self.assertEqual(rows[1]["movies_count"], 3, "movies_count is wrong.")
        self.assertEqual(rows[1]["owner_username"], "ivan")

    def test_09_hidden_playlists_disappear(self):
        """A playlist its owner made private disappears from the library"""
        self.client.put(self.save_url(self.public))
        Playlist.objects.filter(pk=self.public.pk).update(is_public=False)
        rows = self.results(self.client.get(self.library_url()))
        self.assertEqual(rows, [], "A playlist hidden by its owner is still visible in another user's library.")
        self.assertTrue(SavedPlaylist.objects.exists(),
                        "The record must be kept: the owner may make the playlist public again.")

    def test_10_library_has_no_n_plus_one(self):
        """The library makes the same number of queries for 2 and for 8 playlists"""
        playlists = [Playlist.objects.create(owner=self.ivan, name=f"P{i}", is_public=True) for i in range(8)]
        for p in playlists[:2]:
            SavedPlaylist.objects.create(user=self.fan, playlist=p)
        with CaptureQueriesContext(connection) as small:
            self.client.get(self.library_url())
        for p in playlists[2:]:
            SavedPlaylist.objects.create(user=self.fan, playlist=p)
        with CaptureQueriesContext(connection) as big:
            self.client.get(self.library_url())
        self.assertEqual(len(big), len(small),
                         f"2 playlists took {len(small)} queries, 8 took {len(big)}. This is N+1: the owner and "
                         "the movie count are fetched one by one. Use select_related + annotate(Count(...)).")

    def test_11_playlist_deleted(self):
        """Deleting a playlist deletes its saves as well"""
        self.client.put(self.save_url(self.public))
        self.public.delete()
        self.assertFalse(SavedPlaylist.objects.exists(), "playlist needs on_delete=models.CASCADE.")
