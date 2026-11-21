"""Liked Titles: the private Favourite playlist every user gets, and the hearts on movie covers."""
import importlib
import re

from django.apps import apps as global_apps
from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import translation
from rest_framework.test import APITestCase

from accounts.models import User
from .models import (
    KindChoice, LIKED_TITLES_NAME, Movie, Playlist, PlaylistItem, Review, WatchStatus,
)
from .services.liked_titles import ensure_liked_titles

HEART = 'data-like-movie="{}"'


def make_user(username):
    return User.objects.create_user(username=username, email=f"{username}@example.com", password="pw-12345!")


def liked_titles(user):
    return Playlist.objects.get(owner=user, kind=KindChoice.FAVOURITE)


class LikedTitlesCreationTests(TestCase):
    def test_new_user_gets_one_private_liked_titles_playlist(self):
        user = make_user("newcomer")
        playlists = Playlist.objects.filter(owner=user)
        self.assertEqual(playlists.count(), 1)
        playlist = playlists.get()
        self.assertEqual(playlist.kind, KindChoice.FAVOURITE)
        self.assertEqual(playlist.name, LIKED_TITLES_NAME)
        self.assertFalse(playlist.is_public)

    def test_saving_the_user_again_does_not_add_another(self):
        user = make_user("returning")
        user.first_name = "Changed"
        user.save()
        self.assertEqual(Playlist.objects.filter(owner=user, kind=KindChoice.FAVOURITE).count(), 1)

    def test_ensure_liked_titles_is_idempotent(self):
        user = make_user("twice")
        first = ensure_liked_titles(user)
        self.assertEqual(ensure_liked_titles(user), first)
        self.assertEqual(Playlist.objects.filter(owner=user, kind=KindChoice.FAVOURITE).count(), 1)

    def test_data_migration_creates_missing_and_makes_public_ones_private(self):
        migration = importlib.import_module("movies.migrations.0055_create_liked_titles")
        without = make_user("without")
        liked_titles(without).delete()
        public = make_user("public")
        Playlist.objects.filter(pk=liked_titles(public).pk).update(is_public=True)
        untouched = liked_titles(make_user("untouched"))

        migration.create_liked_titles(global_apps, None)

        created = liked_titles(without)
        self.assertEqual(created.name, LIKED_TITLES_NAME)
        self.assertFalse(created.is_public)
        self.assertFalse(liked_titles(public).is_public)
        self.assertEqual(liked_titles(untouched.owner).pk, untouched.pk)
        self.assertEqual(Playlist.objects.filter(kind=KindChoice.FAVOURITE).count(), User.objects.count())

    def test_display_name_is_translated_only_for_liked_titles(self):
        user = make_user("reader")
        custom = Playlist.objects.create(owner=user, name="Weekend")
        with translation.override("ru"):
            self.assertEqual(str(liked_titles(user).display_name), "Избранное")
            self.assertEqual(custom.display_name, "Weekend")
        with translation.override("en"):
            self.assertEqual(str(liked_titles(user).display_name), "Liked Titles")


class LikedTitlesAPITests(APITestCase):
    """The hearts use only the existing playlist API; these are the calls liked-titles.js makes."""

    def setUp(self):
        self.user = make_user("liker")
        self.movie = Movie.objects.create(name="Loved")
        self.liked = liked_titles(self.user)
        self.client.force_authenticate(self.user)

    def item_url(self, movie):
        return reverse("movies:playlist_item_api", kwargs={"pl_id": self.liked.pk, "movie_id": movie.pk})

    def test_heart_state_is_loaded_from_the_list_and_detail_endpoints(self):
        PlaylistItem.objects.create(playlist=self.liked, movie=self.movie)
        playlists = self.client.get(reverse("movies:playlist_create_api")).json()
        favourite = next(row for row in playlists if row["kind"] == KindChoice.FAVOURITE)
        self.assertEqual(favourite["id"], self.liked.pk)
        detail = self.client.get(reverse("movies:playlist_api", kwargs={"pl_id": favourite["id"]})).json()
        self.assertEqual([item["movie"]["id"] for item in detail["items"]], [self.movie.pk])

    def test_like_and_unlike(self):
        response = self.client.put(self.item_url(self.movie))
        self.assertEqual(response.status_code, 201)
        self.assertTrue(PlaylistItem.objects.filter(playlist=self.liked, movie=self.movie).exists())
        response = self.client.delete(self.item_url(self.movie))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(PlaylistItem.objects.filter(playlist=self.liked, movie=self.movie).exists())

    def test_liking_does_not_touch_the_watch_status(self):
        self.client.put(self.item_url(self.movie))
        self.assertFalse(WatchStatus.objects.filter(user=self.user, movie=self.movie).exists())

    def test_cannot_like_into_someone_elses_liked_titles(self):
        other = liked_titles(make_user("other"))
        url = reverse("movies:playlist_item_api", kwargs={"pl_id": other.pk, "movie_id": self.movie.pk})
        self.assertEqual(self.client.put(url).status_code, 404)
        self.assertFalse(other.items.exists())

    def test_liked_titles_is_hidden_from_other_users(self):
        url = reverse("movies:playlist_api", kwargs={"pl_id": self.liked.pk})
        self.client.force_authenticate(make_user("stranger"))
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_cover_can_be_reset_to_the_default(self):
        # The trash button on the playlist page sends PATCH {"cover": null}.
        Playlist.objects.filter(pk=self.liked.pk).update(cover="playlists/covers/mine.png")
        url = reverse("movies:playlist_api", kwargs={"pl_id": self.liked.pk})
        response = self.client.patch(url, {"cover": None}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["cover"])
        self.liked.refresh_from_db()
        self.assertFalse(self.liked.cover)
        self.assertFalse(self.liked.is_public)


class LikedTitlesPagesTests(TestCase):
    def setUp(self):
        self.user = make_user("owner")
        self.liked = liked_titles(self.user)
        self.movie = Movie.objects.create(name="Poster movie", year=2020, cover_url="/poster.jpg")

    def test_profile_shows_liked_titles_right_after_the_create_tile(self):
        Playlist.objects.create(owner=self.user, name="Newer custom")
        self.client.force_login(self.user)
        response = self.client.get(reverse("profile", args=[self.user.username]))
        html = response.content.decode()
        self.assertEqual(response.context["playlists"][0].pk, self.liked.pk)
        grid = html[html.index("data-playlists-list"):html.index("data-playlists-empty")]
        tile, first_card = grid.index("profile-playlist-new"), grid.index("profile-playlist-card")
        self.assertLess(tile, first_card)
        self.assertIn(f'data-playlist-id="{self.liked.pk}"', grid[first_card:first_card + 300])
        self.assertIn("images/favPl.png", grid)
        self.assertIn("<span>Liked Titles</span>", grid)

    def test_profile_shows_translated_name(self):
        self.client.force_login(self.user)
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ru"
        response = self.client.get(reverse("profile", args=[self.user.username]))
        self.assertContains(response, "<span>Избранное</span>")

    def test_custom_cover_replaces_the_default(self):
        Playlist.objects.filter(pk=self.liked.pk).update(cover="playlists/covers/mine.png")
        self.client.force_login(self.user)
        response = self.client.get(reverse("profile", args=[self.user.username]))
        self.assertContains(response, "playlists/covers/mine.png")
        self.assertNotContains(response, "images/favPl.png")

    def test_visitors_do_not_see_liked_titles(self):
        self.client.force_login(make_user("visitor"))
        response = self.client.get(reverse("profile", args=[self.user.username]))
        self.assertNotIn(self.liked.pk, [p.pk for p in response.context["playlists"]])

    def test_playlist_page_allows_cover_but_not_rename_delete_or_privacy(self):
        PlaylistItem.objects.create(playlist=self.liked, movie=self.movie)
        self.client.force_login(self.user)
        response = self.client.get(reverse("movies:playlist", args=[self.liked.pk]))
        self.assertContains(response, '<h1 class="playlist-title" data-playlist-name>Liked Titles</h1>', html=True)
        self.assertContains(response, 'data-action="change-cover"')
        self.assertContains(response, "images/favPl.png")
        self.assertContains(response, "playlist-private-note")
        self.assertNotContains(response, "data-playlist-public")
        self.assertNotContains(response, 'data-action="rename"')
        self.assertNotContains(response, 'data-action="delete-playlist"')
        self.assertContains(response, HEART.format(self.movie.pk))

    def reset_button(self, playlist):
        self.client.force_login(self.user)
        html = self.client.get(reverse("movies:playlist", args=[playlist.pk])).content.decode()
        match = re.search(r'<button class="playlist-cover-reset".*?>', html, re.S)
        return match.group(0) if match else None

    def test_reset_button_appears_only_for_an_uploaded_cover(self):
        button = self.reset_button(self.liked)
        self.assertIn("hidden", button)
        Playlist.objects.filter(pk=self.liked.pk).update(cover="playlists/covers/mine.png")
        button = self.reset_button(self.liked)
        self.assertNotIn("hidden", button)
        self.assertIn('aria-label="Restore the default cover"', button)
        self.assertIn('data-tooltip="Restore the default cover"', button)

    def test_reset_button_removes_the_cover_of_a_custom_playlist(self):
        custom = Playlist.objects.create(owner=self.user, name="Mine", cover="playlists/covers/mine.png")
        button = self.reset_button(custom)
        self.assertIn('aria-label="Remove cover"', button)
        self.assertNotIn("data-default-cover", self.client.get(reverse("movies:playlist", args=[custom.pk])).content.decode())

    def test_reset_button_label_is_translated(self):
        Playlist.objects.filter(pk=self.liked.pk).update(cover="playlists/covers/mine.png")
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ru"
        self.assertIn('data-tooltip="Вернуть обложку по умолчанию"', self.reset_button(self.liked))

    def test_no_reset_button_for_visitors(self):
        custom = Playlist.objects.create(
            owner=self.user, name="Shared", is_public=True, cover="playlists/covers/mine.png",
        )
        self.client.force_login(make_user("guest"))
        response = self.client.get(reverse("movies:playlist", args=[custom.pk]))
        self.assertNotContains(response, "playlist-cover-reset")

    def test_custom_playlist_page_keeps_its_controls(self):
        custom = Playlist.objects.create(owner=self.user, name="Mine")
        self.client.force_login(self.user)
        response = self.client.get(reverse("movies:playlist", args=[custom.pk]))
        for marker in ("data-playlist-public", 'data-action="rename"', 'data-action="delete-playlist"'):
            self.assertContains(response, marker)
        self.assertNotContains(response, "playlist-private-note")


class LikeHeartRenderingTests(TestCase):
    def setUp(self):
        self.user = make_user("viewer")
        self.movie = Movie.objects.create(name="Heart movie", year=2021, cover_url="/poster.jpg")
        self.heart = HEART.format(self.movie.pk)

    def get(self, url, login=True):
        if login:
            self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_hearts_on_every_movie_cover_for_signed_in_users(self):
        WatchStatus.objects.create(user=self.user, movie=self.movie, status=WatchStatus.StatusChoice.VIEWED)
        playlist = Playlist.objects.create(owner=self.user, name="With movie")
        PlaylistItem.objects.create(playlist=playlist, movie=self.movie)
        # The reviews feed lists only reviews with text.
        Review.objects.create(user=self.user, movie=self.movie, rating=8, text="Worth it")
        pages = {
            "catalog": reverse("movies:catalog"),
            "movie": reverse("movies:detail", args=[self.movie.pk]),
            "playlist": reverse("movies:playlist", args=[playlist.pk]),
            "review form": reverse("movies:review_form", args=[self.movie.pk]),
            "reviews feed": reverse("movies:show_reviews"),
            "profile library": reverse("profile", args=[self.user.username]),
        }
        for name, url in pages.items():
            with self.subTest(page=name):
                self.assertIn(self.heart, self.get(url))

    def test_hearts_are_outside_links(self):
        # A <button> inside <a> is invalid HTML and would follow the link on click.
        for url in (reverse("movies:catalog"), reverse("movies:show_reviews")):
            html = self.get(url)
            for link in re.findall(r"<a\b.*?</a>", html, re.S):
                self.assertNotIn("data-like-movie", link)

    def test_movie_page_uses_the_large_heart(self):
        html = self.get(reverse("movies:detail", args=[self.movie.pk]))
        self.assertRegex(html, r'class="like-heart like-heart--lg"\s+type="button"\s+' + re.escape(self.heart))
        self.assertIn('data-liked-titles-label="Liked Titles"', html)

    def test_no_hearts_or_liked_titles_script_for_anonymous_visitors(self):
        html = self.get(reverse("movies:detail", args=[self.movie.pk]), login=False)
        self.assertNotIn("data-like-movie", html)
        self.assertNotIn("data-liked-titles", html)
        self.assertNotIn("liked-titles.js", html)

    def test_signed_in_pages_load_settings_template_and_script(self):
        html = self.get(reverse("movies:catalog"))
        self.assertIn("data-liked-titles", html)
        self.assertIn("data-like-heart-template", html)
        self.assertIn(HEART.format("__MOVIE__"), html)
        self.assertIn("liked-titles.js", html)

    def test_api_helper_is_loaded_once_per_page(self):
        # api.js declares a class at top level: loading it twice is a SyntaxError in the browser.
        playlist = Playlist.objects.create(owner=self.user, name="Once")
        for url in (
            reverse("movies:detail", args=[self.movie.pk]),
            reverse("movies:playlist", args=[playlist.pk]),
            reverse("profile", args=[self.user.username]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.get(url).count("movies/js/api.js"), 1)
