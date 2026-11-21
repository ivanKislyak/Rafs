import io
import tempfile
from unittest import skipUnless

from PIL import Image
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User
from .models import (
    GlobalSearchIndex, KindChoice, Movie, Playlist, PlaylistItem,
    PLAYLISTS_PER_USER_LIMIT, PLAYLIST_NAME_MAX_LENGTH,
)


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
            "is_public": self.playlist.is_public,
            "items": []
        }

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected_response)

    def test_user_cant_read_other_private_playlist(self):
        other_user = User.objects.create_user(
            username='other_user',
            email='other_user_email@mail.com'
        )
        other_private_playlist = Playlist.objects.create(
            name="My Private Playlist",
            owner=other_user,
            kind=KindChoice.CUSTOM,
            is_public=False
        )
        response = self.client.get(
            reverse('movies:playlist_api', kwargs={"pl_id": other_private_playlist.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_authenticated_user_put_existing_playlist(self):
        raw_data = {
            "name": "My private Playlist",
            "is_public": False,
        }

        response = self.client.put(self.url, data=raw_data, format="json")
        expected_response = {
            "id": self.playlist.pk,
            "name": "My private Playlist",
            "kind": self.playlist.kind,
            "owner": self.user.pk,
            "cover": None,
            "is_public": False,
            "items": []
        }
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected_response)


class PlaylistTestMixin:
    @staticmethod
    def make_user(username):
        return User.objects.create_user(username=username, email=f"{username}@example.com")


class PlaylistCreateAPITests(PlaylistTestMixin, APITestCase):
    def setUp(self):
        self.user = self.make_user("creator")
        self.url = reverse("movies:playlist_create_api")

    def test_anonymous_user_cannot_create(self):
        response = self.client.post(self.url, {"name": "Anon"}, format="json")
        self.assertIn(response.status_code, (401, 403))
        self.assertFalse(Playlist.objects.filter(name="Anon").exists())

    def test_create_sets_owner_and_ignores_kind(self):
        other = self.make_user("other")
        self.client.force_authenticate(self.user)
        response = self.client.post(
            self.url,
            {"name": "  Weekend  ", "kind": KindChoice.FAVOURITE, "owner": other.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        playlist = Playlist.objects.get(pk=response.json()["id"])
        self.assertEqual(playlist.owner, self.user)
        self.assertEqual(playlist.kind, KindChoice.CUSTOM)
        self.assertEqual(playlist.name, "Weekend")
        self.assertFalse(playlist.is_public)

    def test_blank_or_whitespace_name_is_rejected(self):
        self.client.force_authenticate(self.user)
        for name in ["", "   ", "\t\n"]:
            with self.subTest(name=repr(name)):
                response = self.client.post(self.url, {"name": name}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn("name", response.json())
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Playlist.objects.filter(owner=self.user).exists())

    def test_name_length_limit(self):
        self.client.force_authenticate(self.user)
        too_long = self.client.post(
            self.url, {"name": "x" * (PLAYLIST_NAME_MAX_LENGTH + 1)}, format="json",
        )
        self.assertEqual(too_long.status_code, 400)
        fits = self.client.post(self.url, {"name": "x" * PLAYLIST_NAME_MAX_LENGTH}, format="json")
        self.assertEqual(fits.status_code, 201)

    def test_multipart_create_with_cover_and_privacy(self):
        # The profile "New playlist" dialog sends name, is_public and cover in one multipart POST.
        image = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(image, format="PNG")
        cover = SimpleUploadedFile("cover.png", image.getvalue(), content_type="image/png")
        self.client.force_authenticate(self.user)
        with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                self.url, {"name": "With cover", "is_public": "true", "cover": cover}, format="multipart",
            )
            self.assertEqual(response.status_code, 201)
            playlist = Playlist.objects.get(pk=response.json()["id"])
            self.assertTrue(playlist.is_public)
            self.assertTrue(playlist.cover.name.startswith("playlists/covers/"))

    def test_multipart_create_with_invalid_cover_creates_nothing(self):
        not_an_image = SimpleUploadedFile("cover.png", b"not an image", content_type="image/png")
        self.client.force_authenticate(self.user)
        response = self.client.post(
            self.url, {"name": "Broken", "is_public": "false", "cover": not_an_image}, format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("cover", response.json())
        self.assertFalse(Playlist.objects.filter(owner=self.user).exists())

    def test_playlist_limit_per_user(self):
        Playlist.objects.bulk_create(
            Playlist(owner=self.user, name=f"List {index}")
            for index in range(PLAYLISTS_PER_USER_LIMIT)
        )
        self.client.force_authenticate(self.user)
        response = self.client.post(self.url, {"name": "One too many"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIsInstance(response.json()["detail"], str)
        self.assertEqual(Playlist.objects.filter(owner=self.user).count(), PLAYLISTS_PER_USER_LIMIT)

        # The limit is per user: someone else can still create playlists.
        self.client.force_authenticate(self.make_user("fresh"))
        self.assertEqual(
            self.client.post(self.url, {"name": "Mine"}, format="json").status_code, 201,
        )


class PlaylistListAPITests(PlaylistTestMixin, APITestCase):
    def setUp(self):
        self.user = self.make_user("lister")
        self.other = self.make_user("stranger")
        self.movie = Movie.objects.create(name="Listed movie")
        self.other_movie = Movie.objects.create(name="Other movie")
        self.with_movie = Playlist.objects.create(owner=self.user, name="With movie")
        self.without_movie = Playlist.objects.create(owner=self.user, name="Without movie")
        PlaylistItem.objects.create(playlist=self.with_movie, movie=self.movie)
        PlaylistItem.objects.create(playlist=self.with_movie, movie=self.other_movie)
        PlaylistItem.objects.create(playlist=self.without_movie, movie=self.other_movie)
        Playlist.objects.create(owner=self.other, name="Foreign", is_public=True)
        self.url = reverse("movies:playlist_create_api")
        self.client.force_authenticate(self.user)

    def test_lists_only_own_playlists_with_counts(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = {row["id"]: row for row in response.json()}
        self.assertEqual(set(data), {self.with_movie.pk, self.without_movie.pk})
        self.assertEqual(data[self.with_movie.pk]["movies_count"], 2)
        self.assertEqual(data[self.without_movie.pk]["movies_count"], 1)
        self.assertIsNone(data[self.with_movie.pk]["contains_movie"])

    def test_contains_movie_flag(self):
        response = self.client.get(self.url, {"movie_id": self.movie.pk})
        self.assertEqual(response.status_code, 200)
        flags = {row["id"]: row["contains_movie"] for row in response.json()}
        self.assertEqual(flags, {self.with_movie.pk: True, self.without_movie.pk: False})

    def test_invalid_movie_id_is_rejected(self):
        response = self.client.get(self.url, {"movie_id": "abc"})
        self.assertEqual(response.status_code, 400)

    def test_query_count_does_not_grow_with_playlists(self):
        def count_queries():
            with CaptureQueriesContext(connection) as context:
                response = self.client.get(self.url, {"movie_id": self.movie.pk})
            self.assertEqual(response.status_code, 200)
            return len(context.captured_queries), len(response.json())

        before, rows_before = count_queries()
        for index in range(5):
            playlist = Playlist.objects.create(owner=self.user, name=f"Extra {index}")
            PlaylistItem.objects.create(playlist=playlist, movie=self.movie)
        after, rows_after = count_queries()

        self.assertEqual(rows_after, rows_before + 5)
        self.assertEqual(after, before)
        self.assertEqual(after, 1)


class PlaylistUpdateDeleteAPITests(PlaylistTestMixin, APITestCase):
    def setUp(self):
        self.user = self.make_user("editor")
        self.other = self.make_user("intruder")
        self.playlist = Playlist.objects.create(owner=self.user, name="Original")
        self.favourite = Playlist.objects.create(
            owner=self.user, name="Favourite", kind=KindChoice.FAVOURITE,
        )
        self.client.force_authenticate(self.user)

    @staticmethod
    def url(playlist):
        return reverse("movies:playlist_api", kwargs={"pl_id": playlist.pk})

    def test_patch_renames_and_keeps_other_fields(self):
        self.playlist.is_public = True
        self.playlist.save()
        response = self.client.patch(self.url(self.playlist), {"name": " Renamed "}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "Renamed")
        self.playlist.refresh_from_db()
        self.assertEqual(self.playlist.name, "Renamed")
        self.assertTrue(self.playlist.is_public)

    def test_patch_toggles_visibility_only(self):
        response = self.client.patch(self.url(self.playlist), {"is_public": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.playlist.refresh_from_db()
        self.assertTrue(self.playlist.is_public)
        self.assertEqual(self.playlist.name, "Original")

    def test_patch_blank_name_is_rejected(self):
        response = self.client.patch(self.url(self.playlist), {"name": "   "}, format="json")
        self.assertEqual(response.status_code, 400)
        self.playlist.refresh_from_db()
        self.assertEqual(self.playlist.name, "Original")

    def test_patch_foreign_playlist_returns_404(self):
        foreign = Playlist.objects.create(owner=self.other, name="Theirs", is_public=True)
        response = self.client.patch(self.url(foreign), {"name": "Hijacked"}, format="json")
        self.assertEqual(response.status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual(foreign.name, "Theirs")

    def test_delete_custom_playlist(self):
        response = self.client.delete(self.url(self.playlist))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Playlist.objects.filter(pk=self.playlist.pk).exists())

    def test_delete_missing_or_foreign_playlist_returns_404(self):
        foreign = Playlist.objects.create(owner=self.other, name="Theirs")
        self.assertEqual(self.client.delete(self.url(foreign)).status_code, 404)
        self.assertTrue(Playlist.objects.filter(pk=foreign.pk).exists())
        missing = reverse("movies:playlist_api", kwargs={"pl_id": 999999})
        self.assertEqual(self.client.delete(missing).status_code, 404)

    def test_favourite_cannot_be_deleted(self):
        response = self.client.delete(self.url(self.favourite))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Playlist.objects.filter(pk=self.favourite.pk).exists())

    def test_favourite_cannot_be_renamed(self):
        for method in (self.client.patch, self.client.put):
            with self.subTest(method=method.__name__):
                response = method(
                    self.url(self.favourite), {"name": "Not favourite", "is_public": False}, format="json",
                )
                self.assertEqual(response.status_code, 403)
        self.favourite.refresh_from_db()
        self.assertEqual(self.favourite.name, "Favourite")

    def test_favourite_visibility_can_change(self):
        # playlist-page.js sends PUT with the current name when toggling visibility.
        response = self.client.put(
            self.url(self.favourite), {"name": "Favourite", "is_public": True}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.patch(self.url(self.favourite), {"is_public": False}, format="json")
        self.assertEqual(response.status_code, 200)

    def test_item_put_returns_movie_with_request_context(self):
        movie = Movie.objects.create(name="Added")
        response = self.client.put(
            reverse("movies:playlist_item_api", kwargs={"pl_id": self.playlist.pk, "movie_id": movie.pk}),
            {}, format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["movie"]["id"], movie.pk)


class ProfilePlaylistsTests(PlaylistTestMixin, TestCase):
    def setUp(self):
        self.owner = self.make_user("collector")
        self.visitor = self.make_user("visitor")
        self.public = Playlist.objects.create(owner=self.owner, name="Shown to all", is_public=True)
        self.private = Playlist.objects.create(owner=self.owner, name="Secret stash")
        self.url = reverse("profile", kwargs={"username": self.owner.username})

    def test_visitor_sees_only_public_playlists(self):
        self.client.force_login(self.visitor)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p.pk for p in response.context["playlists"]], [self.public.pk])
        self.assertContains(response, "Shown to all")
        self.assertNotContains(response, "Secret stash")
        self.assertNotContains(response, "data-create-dialog")

    def test_anonymous_sees_only_public_playlists(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Shown to all")
        self.assertNotContains(response, "Secret stash")

    def test_owner_sees_all_playlists_and_create_dialog(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(
            {p.pk for p in response.context["playlists"]}, {self.public.pk, self.private.pk},
        )
        self.assertContains(response, "Secret stash")
        self.assertContains(response, "data-create-dialog")
        self.assertContains(response, "profile-playlist-lock", count=1)

    def test_section_hidden_for_visitor_without_public_playlists(self):
        self.public.delete()
        response = self.client.get(self.url)
        self.assertNotContains(response, "data-playlists")

    def test_owner_without_playlists_sees_empty_state(self):
        Playlist.objects.filter(owner=self.owner).delete()
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertContains(response, "data-playlists-empty")
        self.assertContains(response, 'data-action="open-create"')

    def test_query_count_does_not_grow_with_playlists(self):
        movie = Movie.objects.create(name="Cover source", cover_url="/poster.jpg")

        def count_queries():
            with CaptureQueriesContext(connection) as context:
                response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            return len(context.captured_queries)

        before = count_queries()
        for index in range(4):
            playlist = Playlist.objects.create(owner=self.owner, name=f"More {index}", is_public=True)
            PlaylistItem.objects.create(playlist=playlist, movie=movie)
        after = count_queries()
        self.assertEqual(after, before)


@skipUnless(connection.vendor == "postgresql", "Full-text search requires PostgreSQL")
class PlaylistSearchTests(PlaylistTestMixin, APITestCase):
    def setUp(self):
        self.owner = self.make_user("searchowner")
        self.playlist = Playlist.objects.create(
            owner=self.owner, name="Zeppelinwatch marathon", is_public=True,
        )
        self.url = reverse("movies:search_results_api")

    def search(self, query="zeppelinwatch"):
        response = self.client.get(self.url, {"query": query})
        self.assertEqual(response.status_code, 200)
        return [row for row in response.json()["results"] if row and row["type"] == "playlist"]

    def document(self):
        return GlobalSearchIndex.objects.filter(
            content_type=ContentType.objects.get_for_model(Playlist), object_id=self.playlist.pk,
        )

    def test_public_playlist_is_found(self):
        results = self.search()
        self.assertEqual([row["id"] for row in results], [self.playlist.pk])
        self.assertEqual(results[0]["url"], reverse("movies:playlist", args=[self.playlist.pk]))
        self.assertEqual(results[0]["title"], "Zeppelinwatch marathon")
        self.assertEqual(results[0]["description"], "@searchowner")

    def test_found_by_owner_username(self):
        self.assertEqual([row["id"] for row in self.search("searchowner")], [self.playlist.pk])

    def test_private_playlist_is_never_indexed_or_found(self):
        private = Playlist.objects.create(owner=self.owner, name="Zeppelinwatch secret")
        self.assertFalse(GlobalSearchIndex.objects.filter(
            content_type=ContentType.objects.get_for_model(Playlist), object_id=private.pk,
        ).exists())
        self.assertNotIn(private.pk, [row["id"] for row in self.search()])

    def test_not_found_after_switching_to_private(self):
        self.client.force_authenticate(self.owner)
        response = self.client.patch(
            reverse("movies:playlist_api", kwargs={"pl_id": self.playlist.pk}),
            {"is_public": False}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.document().exists())
        self.assertEqual(self.search(), [])

    def test_stale_document_of_private_playlist_is_filtered(self):
        # Bypass signals (queryset.update) to simulate an out-of-date index.
        Playlist.objects.filter(pk=self.playlist.pk).update(is_public=False)
        self.assertTrue(self.document().exists())
        self.assertEqual(self.search(), [])

    def test_rename_updates_document(self):
        self.playlist.name = "Airshipnight"
        self.playlist.save()
        self.assertEqual(self.search(), [])
        self.assertEqual([row["id"] for row in self.search("airshipnight")], [self.playlist.pk])

    def test_not_found_after_delete(self):
        self.client.force_authenticate(self.owner)
        response = self.client.delete(
            reverse("movies:playlist_api", kwargs={"pl_id": self.playlist.pk}),
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(self.document().exists())
        self.assertEqual(self.search(), [])

    def test_playlists_of_deleted_owner_are_hidden(self):
        User.objects.filter(pk=self.owner.pk).update(is_deleted=True)
        self.assertEqual(self.search(), [])
