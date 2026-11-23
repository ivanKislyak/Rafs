from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, reverse
from rest_framework.test import APITestCase

from accounts.models import User
from movies.models import Movie, Playlist, PlaylistItem

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


class PlaylistOrderAPITests(RecordingMixin, APITestCase):
    def setUp(self):
        self.ivan = User.objects.create_user(username="ivan", email="ivan@rafs.test")
        self.playlist = Playlist.objects.create(owner=self.ivan, name="Carrey marathon", is_public=True)
        self.bruce = Movie.objects.create(name="Bruce Almighty", year=2003)
        self.mask = Movie.objects.create(name="The Mask", year=1994)
        self.truman = Movie.objects.create(name="The Truman Show", year=1998)
        for position, movie in enumerate([self.bruce, self.mask, self.truman], start=1):
            PlaylistItem.objects.create(playlist=self.playlist, movie=movie, position=position)
        try:
            self.url = reverse("movies:playlist_order_api", kwargs={"pl_external_id": self.playlist.external_id})
        except NoReverseMatch:
            self.fail("Route movies:playlist_order_api not found. Add a path(...) with name='playlist_order_api' "
                      "to movies/urls.py, using the <slug:pl_external_id> parameter.")
        self.client.force_authenticate(user=self.ivan)

    def order(self, playlist=None):
        return list(PlaylistItem.objects.filter(playlist=playlist or self.playlist)
                    .order_by("position", "pk").values_list("movie_id", flat=True))

    def positions(self, playlist=None):
        return list(PlaylistItem.objects.filter(playlist=playlist or self.playlist)
                    .order_by("position", "pk").values_list("position", flat=True))

    def assertUnchanged(self):
        self.assertEqual(self.order(), [self.bruce.pk, self.mask.pk, self.truman.pk],
                         "The order in the database changed after a rejected request. "
                         "All checks must happen BEFORE writing.")

    def test_01_reorder_is_saved(self):
        """The new order is saved: positions 1..n in the new order"""
        new_order = [self.truman.pk, self.bruce.pk, self.mask.pk]
        response = self.api("put", self.url, {"movie_ids": new_order}, label="success: new order")
        self.assertIn(response.status_code, (200, 204),
                      f"Expected 200 or 204, got {response.status_code}: {getattr(response, 'data', '')}")
        self.assertEqual(self.order(), new_order,
                         "The response came back, but the database still has the old order: positions were not saved.")
        self.assertEqual(self.positions(), [1, 2, 3],
                         f"Positions must be exactly 1, 2, 3, but the database has {self.positions()}. "
                         "Hint: enumerate(..., start=1).")
        if response.status_code == 200 and isinstance(response.data, dict) and "movie_ids" in response.data:
            self.assertEqual(list(response.data["movie_ids"]), new_order,
                             "movie_ids in the response does not match what was saved.")

    def test_02_missing_movie_rejected(self):
        """A missing movie gives 400 and the order stays untouched"""
        response = self.api("put", self.url, {"movie_ids": [self.mask.pk, self.bruce.pk]},
                            label="error: movie missing")
        self.assertEqual(response.status_code, 400,
                         f"Expected 400, got {response.status_code}. {self.truman.pk} is missing from the body: "
                         "what position would it get? Compare the two sets of movies.")
        self.assertIn("movie_ids", response.data,
                      "It is better to return the error under the movie_ids key, as a field error.")
        self.assertUnchanged()

    def test_03_foreign_movie_rejected(self):
        """An extra movie that is not in the playlist gives 400"""
        ace = Movie.objects.create(name="Ace Ventura", year=1994)
        body = {"movie_ids": [self.bruce.pk, self.mask.pk, self.truman.pk, ace.pk]}
        response = self.api("put", self.url, body, label="error: foreign movie")
        self.assertEqual(response.status_code, 400,
                         f"Expected 400, got {response.status_code}. Reordering does not add movies, "
                         "that is what PUT items/<id>/ is for.")
        self.assertFalse(PlaylistItem.objects.filter(playlist=self.playlist, movie=ace).exists(),
                         "A movie that was not in the playlist has appeared in it.")
        self.assertUnchanged()

    def test_04_duplicates_rejected(self):
        """A duplicate gives 400, even when set() matches"""
        body = {"movie_ids": [self.bruce.pk, self.bruce.pk, self.mask.pk, self.truman.pk]}
        response = self.api("put", self.url, body, label="error: duplicate")
        self.assertEqual(response.status_code, 400,
                         f"Expected 400, got {response.status_code}. set() collapses duplicates and then equals "
                         "the playlist, so a separate length check is needed.")
        self.assertUnchanged()

    def test_05_missing_field(self):
        """No movie_ids field gives 400 with an error on that field"""
        response = self.api("put", self.url, {"order": [self.bruce.pk]}, label="error: field missing")
        self.assertEqual(response.status_code, 400, f"Expected 400, got {response.status_code}.")
        self.assertIn("movie_ids", response.data, "The serializer should report that movie_ids is required.")

    def test_06_not_a_list(self):
        """movie_ids as a string instead of a list gives 400"""
        response = self.api("put", self.url, {"movie_ids": "1,2,3"}, label="error: not a list")
        self.assertEqual(response.status_code, 400,
                         f"Expected 400, got {response.status_code}. This is ListField's job, "
                         "no need to parse it by hand.")

    def test_07_other_users_playlist(self):
        """Someone else's playlist gives 404 and the order stays untouched"""
        kino_fan = User.objects.create_user(username="kino_fan", email="kino_fan@rafs.test")
        self.client.force_authenticate(user=kino_fan)
        body = {"movie_ids": [self.truman.pk, self.mask.pk, self.bruce.pk]}
        response = self.api("put", self.url, body, label="error: not the owner")
        self.assertEqual(response.status_code, 404,
                         f"Expected 404, got {response.status_code}. "
                         "Look the playlist up among the user's own only (owner=request.user).")
        self.assertUnchanged()

    def test_08_anonymous(self):
        """An anonymous user gets 403"""
        self.client.force_authenticate(user=None)
        body = {"movie_ids": [self.truman.pk, self.mask.pk, self.bruce.pk]}
        response = self.api("put", self.url, body, label="error: anonymous")
        self.assertEqual(response.status_code, 403,
                         f"Expected 403, got {response.status_code}. Check permission_classes.")
        self.assertUnchanged()

    def test_09_same_number_of_queries(self):
        """The number of queries does not grow with the playlist length"""
        big = Playlist.objects.create(owner=self.ivan, name="Big", is_public=True)
        movies = [Movie.objects.create(name=f"Movie {i}") for i in range(20)]
        for position, movie in enumerate(movies, start=1):
            PlaylistItem.objects.create(playlist=big, movie=movie, position=position)
        big_url = reverse("movies:playlist_order_api", kwargs={"pl_external_id": big.external_id})

        with CaptureQueriesContext(connection) as small_ctx:
            self.client.put(self.url, {"movie_ids": [self.truman.pk, self.bruce.pk, self.mask.pk]}, format="json")
        with CaptureQueriesContext(connection) as big_ctx:
            self.client.put(big_url, {"movie_ids": [m.pk for m in reversed(movies)]}, format="json")
        self.assertEqual(self.order(big), [m.pk for m in reversed(movies)], "The big playlist was not reordered.")
        self.assertEqual(len(big_ctx), len(small_ctx),
                         f"3 movies took {len(small_ctx)} queries, 20 movies took {len(big_ctx)}. "
                         "It looks like every movie is saved with its own save(). A single bulk_update fixes this.")

    def test_10_playlist_row_is_locked_first(self):
        """The playlist row is locked (FOR UPDATE) before the movies are read"""
        with CaptureQueriesContext(connection) as ctx:
            self.client.put(self.url, {"movie_ids": [self.truman.pk, self.bruce.pk, self.mask.pk]}, format="json")
        sqls = [q["sql"] for q in ctx.captured_queries]
        lock_index = next((i for i, sql in enumerate(sqls) if "FOR UPDATE" in sql), None)
        self.assertIsNotNone(lock_index,
                             "The playlist is not locked: there is no FOR UPDATE in the SQL. "
                             "Use select_for_update() on the playlist queryset.")
        items_index = next((i for i, sql in enumerate(sqls)
                            if "playlistitem" in sql.lower() and sql.startswith("SELECT")), None)
        if items_index is not None:
            self.assertLess(lock_index, items_index,
                            "The lock is taken AFTER the movies are read: a second tab can change the playlist "
                            "between the two.")