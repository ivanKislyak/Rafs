import json
from html import escape
from unittest.mock import patch
from unittest import skipUnless

from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.search import SearchVector
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Value
from django.test import Client, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, reverse
from django.utils import translation

from .forms import ReviewForm
from .models import GlobalSearchIndex, Movie, Review, ReviewReply, ReviewVote, WatchStatus
from .movie_models import Country, Genre, Person, Studio, TypeOfWork
from .serializers import SearchResultSerializer
from .views import search_page


@skipUnless(connection.vendor == "postgresql", "Search API uses PostgreSQL full-text queries")
class SearchResultsAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = get_user_model().objects.create_user(
            username="search-author", email="search-author@example.com", about="Public profile description",
        )
        cls.deleted = get_user_model().objects.create_user(
            username="hidden-search-user", email="hidden-search@example.com", is_deleted=True,
        )
        cls.movies = [Movie.objects.create(name=f"Base movie {i}", description="Base plot", year=2024) for i in range(27)]
        translated = cls.movies[1]
        for language, name in [("en", "English title"), ("ru", "Русское название")]:
            translated.set_current_language(language)
            translated.wikidata_name = name
            translated.wikidata_description = name + " plot"
            translated.save()
        cls.review = Review.objects.create(
            id=101, user=cls.author, movie=cls.movies[0], rating=8, text='<script>alert(1)</script> Review text',
        )
        cls.entities = [
            Person.objects.create(wikidata_id="CHECK_PERSON", _current_language="en", name="Person", bio="Person biography"),
            Studio.objects.create(wikidata_id="CHECK_STUDIO", _current_language="en", name="Studio"),
            Country.objects.create(wikidata_id="CHECK_COUNTRY", _current_language="en", name="Country"),
            Genre.objects.create(wikidata_id="CHECK_GENRE", _current_language="en", name="Genre"),
            TypeOfWork.objects.create(wikidata_id="CHECK_TYPE", _current_language="en", name="Type"),
        ]
        targets = [*cls.movies, cls.review, cls.author, cls.deleted, *cls.entities]
        for target in targets:
            GlobalSearchIndex.objects.create(
                content_type=ContentType.objects.get_for_model(target), object_id=target.pk,
                search_vector=SearchVector(Value("rafsfixture"), config="english"),
            )
        cls.url = reverse("movies:search_results_api")

    def all_results(self, **headers):
        first = self.client.get(self.url, {"query": "rafsfixture"}, **headers).json()
        last = self.client.get(first["next"], **headers).json()
        return first["results"] + last["results"]

    def test_pagination_uses_25_results_and_stable_order_without_duplicates(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url, {"query": "rafsfixture"})
        self.assertEqual(response.status_code, 200)
        first = response.json()
        self.assertEqual(first["count"], 35)
        self.assertEqual(len(first["results"]), 25)
        self.assertIsNone(first["previous"])
        self.assertIn("page=2", first["next"])
        self.assertTrue(any('movies_globalsearchindex' in q['sql'] and 'LIMIT 25' in q['sql'] for q in queries))
        last = self.client.get(first["next"]).json()
        self.assertEqual(len(last["results"]), 10)
        self.assertIsNone(last["next"])
        actual = [(r["type"], r["id"]) for r in first["results"] + last["results"]]
        expected = list(GlobalSearchIndex.objects.order_by("pk").values_list("content_type__model", "object_id"))
        self.assertEqual(actual, expected)
        self.assertEqual(len(set(actual)), 35)

    def test_all_types_have_correct_links_authors_and_public_metadata(self):
        results = self.all_results()
        self.assertEqual({r["type"] for r in results}, {"movie", "review", "user", "person", "studio", "country", "genre", "typeofwork"})
        review = next(r for r in results if r["type"] == "review")
        self.assertEqual(review["id"], 101)
        self.assertEqual(review["url"], f"/movies/{self.movies[0].pk}/#review-101")
        self.assertEqual(review["title"], self.movies[0].name)
        self.assertEqual(review["description"], self.review.text)
        self.assertEqual(review["author"]["url"], "/@search-author/")
        self.assertEqual(review["author"]["image"], "/static/images/default_profile_img.png")
        self.assertTrue(review["created_at"])
        user = next(r for r in results if r["type"] == "user" and not r["is_deleted"])
        self.assertEqual(user["url"], "/@search-author/")
        self.assertEqual(user["description"], "Public profile description")
        self.assertTrue(user["date_joined"])
        self.assertNotIn("email", user)
        for result in results:
            if result["type"] in {"person", "studio", "country", "genre", "typeofwork"}:
                self.assertIsNone(result["url"])
                self.assertTrue(result["wikidata_id"])

    def test_deleted_user_and_review_author_do_not_expose_profile(self):
        self.review.user = self.deleted
        self.review.save()
        results = self.all_results()
        deleted = next(r for r in results if r["type"] == "user" and r["is_deleted"])
        for field in ["title", "description", "image", "url", "date_joined"]:
            self.assertIsNone(deleted[field])
        author = next(r for r in results if r["type"] == "review")["author"]
        self.assertTrue(author["is_deleted"])
        self.assertIsNone(author["url"])
        self.assertEqual(author["name"], "Deleted user")
        self.assertNotIn(self.deleted.username, json.dumps(author))

    def test_translated_fields_and_plain_field_fallback_work(self):
        results = self.all_results(HTTP_ACCEPT_LANGUAGE="ru")
        movie = next(r for r in results if r["type"] == "movie" and r["id"] == self.movies[1].pk)
        self.assertEqual(movie["title"], "Русское название")
        self.assertEqual(movie["description"], "Русское название plot")
        base = next(r for r in results if r["type"] == "movie" and r["id"] == self.movies[0].pk)
        self.assertEqual(base["title"], "Base movie 0")
        self.assertEqual(base["description"], "Base plot")

    def test_stale_index_entry_does_not_break_api(self):
        GlobalSearchIndex.objects.create(
            content_type=ContentType.objects.get_for_model(Movie), object_id=999999,
            search_vector=SearchVector(Value("rafsfixture"), config="english"),
        )
        results = self.all_results()
        self.assertEqual(len(results), 36)
        self.assertIsNone(results[-1])

    def test_empty_search_does_not_query_search_index(self):
        with self.assertNumQueries(0):
            response = self.client.get(self.url, {"query": "   "})
        self.assertEqual(response.json(), {"count": 0, "next": None, "previous": None, "results": []})

    def test_external_image_priority_and_missing_file_fallback(self):
        movie = self.movies[0]
        movie.cover_url = "https://example.invalid/poster.jpg"
        movie.cover.name = "missing.jpg"
        entry = GlobalSearchIndex.objects.get(content_type=ContentType.objects.get_for_model(Movie), object_id=movie.pk)
        entry.content_object = movie
        serializer = SearchResultSerializer()
        with patch.object(movie.cover.storage, "exists", side_effect=AssertionError("URL takes priority")):
            self.assertEqual(serializer.get_image(entry), movie.cover_url)
        movie.cover_url = ""
        with patch.object(movie.cover.storage, "exists", return_value=False):
            self.assertEqual(serializer.get_image(entry), "/static/movies/images/nocover.png")
        with patch.object(movie.cover.storage, "exists", return_value=True):
            self.assertEqual(serializer.get_image(entry), movie.cover.url)


class ReviewFormTests(SimpleTestCase):
    def test_review_form_contains_expected_fields(self):
        form = ReviewForm()

        self.assertIn("rating", form.fields)
        self.assertIn("text", form.fields)
        self.assertIn("contains_spoiler", form.fields)


class MovieDetailTranslationTests(TestCase):
    languages = ("en", "ru", "uk", "kk", "es", "de")

    @classmethod
    def setUpTestData(cls):
        cls.movie = Movie.objects.create(
            name="Original title", description="Original description", year=2024,
        )
        for language in cls.languages:
            cls.movie.set_current_language(language)
            cls.movie.wikidata_name = f"Localized title {language}"
            cls.movie.wikidata_description = f"Localized description {language}"
            cls.movie.save()

    def assert_displayed_movie(self, movie, language, title, description):
        response = self.client.get(
            reverse("movies:detail", args=[movie.pk]), HTTP_ACCEPT_LANGUAGE=language,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"<h1>{escape(title)}</h1>", html=True)
        self.assertContains(response, f'alt="{escape(title)}"')
        self.assertContains(
            response, f'<p class="movie-detail-main-description">{escape(description)}</p>', html=True,
        )
        return response

    def test_available_translations_are_used_in_content_and_metadata_in_six_languages(self):
        for language in self.languages:
            with self.subTest(language=language):
                title = f"Localized title {language}"
                description = f"Localized description {language}"
                response = self.assert_displayed_movie(self.movie, language, title, description)
                for attributes, value in [
                    ('name="description"', f"{title} (2024) – {description}"),
                    ('property="og:description"', f"{title} (2024) – {description}"),
                    ('property="og:title"', f"{title} (2024) – RAFS"),
                ]:
                    self.assertContains(response, f'<meta {attributes} content="{escape(value)}">', html=True)
                # Browser titles retain the previously requested format and base name.
                with translation.override(language):
                    suffix = translation.gettext("Ratings and reviews")
                self.assertContains(response, f"<title>Original title (2024) – {suffix} · RAFS</title>", html=True)

    def test_translated_description_is_shown_even_when_base_description_is_empty(self):
        self.movie.description = ""
        self.movie.save(update_fields=["description"])
        self.assert_displayed_movie(
            self.movie, "ru", "Localized title ru", "Localized description ru",
        )

    def test_missing_or_empty_translations_fall_back_to_base_fields(self):
        for has_empty_translation in [False, True]:
            movie = Movie.objects.create(name="Fallback title", description="Fallback description")
            if has_empty_translation:
                movie.set_current_language("ru")
                movie.wikidata_name = ""
                movie.wikidata_description = ""
                movie.save()
            with self.subTest(has_empty_translation=has_empty_translation):
                self.assert_displayed_movie(movie, "ru", "Fallback title", "Fallback description")

    def test_translated_fields_remain_escaped_and_meta_description_strips_tags(self):
        self.movie.set_current_language("ru")
        title = 'Название "фильма" <img src=x onerror=alert(1)>'
        description = '<p>Сюжет "с кавычками" & деталями</p>'
        self.movie.wikidata_name = title
        self.movie.wikidata_description = description
        self.movie.save()

        response = self.assert_displayed_movie(self.movie, "ru", title, description)

        self.assertNotContains(response, "<img src=x onerror=alert(1)>")
        expected_meta = f'{title} (2024) – Сюжет "с кавычками" & деталями'
        self.assertContains(
            response, f'<meta name="description" content="{escape(expected_meta)}">', html=True,
        )


class WikidataImportPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(
            username="import-staff", email="import-staff@example.com", is_staff=True,
        )
        cls.visitor = get_user_model().objects.create_user(
            username="import-visitor", email="import-visitor@example.com",
        )
        cls.url = reverse("movies:wikidata_save_item", args=["Q123"])

    @patch("movies.views.fetch_movie_details_raw")
    def test_get_does_not_import_even_for_staff(self, fetch):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.headers["Allow"], "POST")
        fetch.assert_not_called()
        self.assertEqual(Movie.objects.count(), 0)

    @patch("movies.views.fetch_movie_details_raw")
    def test_anonymous_and_non_staff_cannot_import(self, fetch):
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.client.force_login(self.visitor)
        self.assertEqual(self.client.post(self.url).status_code, 302)
        fetch.assert_not_called()
        self.assertEqual(Movie.objects.count(), 0)

    def test_search_result_posts_with_csrf_and_imports_only_after_submit(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        with patch("movies.views.search_wikidata_media", return_value=[{
            "id": "Q123", "title": "Fixture movie", "description": "Fixture description",
        }]), patch("movies.views.fetch_movie_details_raw") as fetch:
            response = client.get(
                reverse("movies:wikidata_search"), {"query": "Fixture", "lang": "en"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f'action="{self.url}"')
            self.assertContains(response, 'method="post"')
            self.assertContains(response, 'name="csrfmiddlewaretoken"')
            self.assertNotContains(response, f'href="{self.url}"')
            self.assertEqual(client.post(self.url).status_code, 403)
            fetch.assert_not_called()

            imported = Movie.objects.create(name="Fixture movie")
            fetch.return_value = {"fixture": "raw"}
            with patch("movies.views.parse_movie_details", return_value={"name": "Fixture movie"}) as parse, patch(
                "movies.views.import_parsed_data_to_db", return_value=imported,
            ) as save:
                response = client.post(
                    self.url, {"csrfmiddlewaretoken": client.cookies["csrftoken"].value},
                )

            self.assertRedirects(response, reverse("movies:detail", args=[imported.pk]))
            fetch.assert_called_once_with("Q123")
            parse.assert_called_once_with({"fixture": "raw"}, "Q123")
            save.assert_called_once_with("Q123", {"name": "Fixture movie"})


class CatalogRatingFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = get_user_model().objects.create_user(
            username="catalog-reviewer",
            password="test-password",
        )
        high_review_rating = Movie.objects.create(
            name="High review rating",
            rate=1,
            year=2020,
        )
        low_review_rating = Movie.objects.create(
            name="Low review rating",
            rate=10,
            year=2021,
        )
        Review.objects.create(user=user, movie=high_review_rating, rating=9)
        Review.objects.create(user=user, movie=low_review_rating, rating=3)

    def test_min_rating_uses_review_average(self):
        response = self.client.get(reverse("movies:catalog"), {"min_rating": 8})
        movies = [movie.name for movie in response.context["page_obj"]]

        self.assertIn("High review rating", movies)
        self.assertNotIn("Low review rating", movies)


class ReviewFramesRewardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="reward-reviewer",
            password="test-password",
        )
        cls.movie = Movie.objects.create(name="Reward test movie", year=2024)

    def setUp(self):
        self.client.force_login(self.user)

    def submit_review(self, text):
        return self.client.post(
            reverse("movies:review_form", args=[self.movie.id]),
            data={"rating": "8.0", "text": text},
            follow=True,
        )

    def test_new_review_rewards_frames_and_displays_notification(self):
        response = self.submit_review("First review")

        self.user.refresh_from_db()
        self.assertEqual(self.user.user_frames, 101)
        self.assertContains(response, "+100 Frames")
        self.assertContains(response, "frames-reward")

    def test_editing_review_does_not_reward_frames_again(self):
        self.submit_review("First review")
        response = self.submit_review("Updated review")

        self.user.refresh_from_db()
        self.assertEqual(self.user.user_frames, 101)
        self.assertNotContains(response, "+100 Frames")


class ReviewVoteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        author = get_user_model().objects.create_user(
            username="review-author",
            email="author@example.com",
        )
        cls.voter = get_user_model().objects.create_user(
            username="review-voter",
            email="voter@example.com",
        )
        movie = Movie.objects.create(name="Vote test movie", year=2020)
        cls.review = Review.objects.create(
            user=author,
            movie=movie,
            rating=8,
            text="Test review",
        )

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.voter)
        self.client.get(reverse("movies:detail", args=[self.review.movie_id]))
        self.csrf_token = self.client.cookies["csrftoken"].value

    def send_vote(self, value):
        return self.client.post(
            reverse("movies:vote_review"),
            data=json.dumps({"review_id": self.review.id, "vote_value": value}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

    def test_like_toggle_and_dislike_switch_are_saved(self):
        like_response = self.send_vote(1)
        self.assertEqual(like_response.status_code, 200)
        self.assertEqual(like_response.json()["likes"], 1)
        self.assertTrue(
            ReviewVote.objects.filter(
                review=self.review,
                user=self.voter,
                value=ReviewVote.VoteChoice.LIKE,
            ).exists()
        )

        remove_response = self.send_vote(1)
        self.assertEqual(remove_response.json()["user_vote"], 0)
        self.assertFalse(
            ReviewVote.objects.filter(review=self.review, user=self.voter).exists()
        )

        dislike_response = self.send_vote(-1)
        self.assertEqual(dislike_response.json()["dislikes"], 1)
        self.assertTrue(
            ReviewVote.objects.filter(
                review=self.review,
                user=self.voter,
                value=ReviewVote.VoteChoice.DISLIKE,
            ).exists()
        )

        detail_response = self.client.get(
            reverse("movies:detail", args=[self.review.movie_id])
        )
        displayed_review = detail_response.context["reviews"][0]
        self.assertEqual(displayed_review.dislike_count, 1)
        self.assertEqual(displayed_review.user_vote, ReviewVote.VoteChoice.DISLIKE)


class ReviewReplyAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = get_user_model().objects.create_user(
            username="api-reply-author", email="api-reply-author@example.com",
        )
        cls.other = get_user_model().objects.create_user(
            username="api-reply-other", email="api-reply-other@example.com",
        )
        cls.movie = Movie.objects.create(name="Reply API movie", year=2025)
        cls.review = Review.objects.create(
            user=cls.other, movie=cls.movie, rating=8, text="Review for replies",
        )
        cls.other_review = Review.objects.create(
            user=cls.author, movie=cls.movie, rating=7, text="Another review",
        )

    def setUp(self):
        self.url = reverse("movies:review_reply_api", args=[self.review.pk])
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.author)
        self.client.get(reverse("movies:detail", args=[self.movie.pk]))
        self.csrf = self.client.cookies["csrftoken"].value

    def post_reply(self, data, url=None):
        return self.client.post(
            url or self.url, json.dumps(data), content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf,
        )

    def test_authenticated_post_creates_reply_and_returns_201(self):
        response = self.post_reply({"text": "A reply from the API"})

        self.assertEqual(response.status_code, 201)
        reply = ReviewReply.objects.get()
        self.assertEqual(reply.text, "A reply from the API")
        self.assertEqual(reply.user_id, self.author.pk)
        self.assertEqual(reply.review_id, self.review.pk)
        self.assertEqual(response.json()["id"], reply.pk)

    def test_payload_cannot_override_author_or_review(self):
        response = self.post_reply({
            "text": "Server owns these relations",
            "user": self.other.pk,
            "review": self.other_review.pk,
        })

        self.assertEqual(response.status_code, 201)
        reply = ReviewReply.objects.get()
        self.assertEqual(reply.user_id, self.author.pk)
        self.assertEqual(reply.review_id, self.review.pk)

    def test_empty_and_whitespace_text_are_rejected(self):
        for text in ("", " \n\t "):
            with self.subTest(text=text):
                response = self.post_reply({"text": text})
                self.assertEqual(response.status_code, 400)
                self.assertIn("text", response.json())
                self.assertFalse(ReviewReply.objects.exists())

    def test_guest_cannot_create_reply(self):
        response = Client().post(
            self.url, {"text": "Anonymous reply"}, content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ReviewReply.objects.exists())

    def test_missing_review_returns_404(self):
        missing_id = max(self.review.pk, self.other_review.pk) + 1000
        response = self.post_reply(
            {"text": "Valid reply"},
            reverse("movies:review_reply_api", args=[missing_id]),
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ReviewReply.objects.exists())

    def test_session_post_requires_csrf(self):
        response = self.client.post(
            self.url, {"text": "No CSRF token"}, content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ReviewReply.objects.exists())

    def test_get_is_public_paginated_and_scoped_to_review(self):
        ReviewReply.objects.bulk_create([
            ReviewReply(user=self.author, review=self.review, text=f"Reply {index}")
            for index in range(26)
        ])
        ReviewReply.objects.create(user=self.other, review=self.other_review, text="Not in this thread")
        guest = Client()

        response = guest.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 26)
        self.assertEqual(len(data["results"]), 25)
        self.assertTrue(all(reply["review"] == self.review.pk for reply in data["results"]))
        following = guest.get(data["next"])
        self.assertEqual(following.status_code, 200)
        self.assertEqual(len(following.json()["results"]), 1)
        self.assertIsNone(following.json()["next"])

    def test_legacy_creation_route_is_removed(self):
        with self.assertRaises(NoReverseMatch):
            reverse("movies:reply_review", args=[self.review.pk])
        response = self.client.post(f"/movies/review/{self.review.pk}/reply/", {"text": "Old endpoint"})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ReviewReply.objects.exists())


class ReviewReplyDisplayTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.first_author = get_user_model().objects.create_user(
            username="first-author",
            email="first-author@example.com",
        )
        cls.second_author = get_user_model().objects.create_user(
            username="second-author",
            email="second-author@example.com",
        )
        cls.reply_author = get_user_model().objects.create_user(
            username="reply-author",
            email="reply-author@example.com",
        )
        cls.movie = Movie.objects.create(name="Replies movie", year=2025)
        cls.first_review = Review.objects.create(
            user=cls.first_author,
            movie=cls.movie,
            rating=8,
            text="First review",
        )
        cls.second_review = Review.objects.create(
            user=cls.second_author,
            movie=cls.movie,
            rating=7,
            text="Second review",
        )
        cls.first_reply = ReviewReply.objects.create(
            review=cls.first_review,
            user=cls.reply_author,
            text="First line\nSecond line",
        )
        cls.second_reply = ReviewReply.objects.create(
            review=cls.second_review,
            user=cls.first_author,
            text="Only for the second review",
        )
        cls.detail_url = reverse("movies:detail", args=[cls.movie.id])

    def test_replies_belong_to_their_own_review(self):
        response = self.client.get(self.detail_url)
        reviews = {review.id: review for review in response.context["reviews"]}

        self.assertEqual(
            [reply.id for reply in reviews[self.first_review.id].loaded_replies],
            [self.first_reply.id],
        )
        self.assertEqual(
            [reply.id for reply in reviews[self.second_review.id].loaded_replies],
            [self.second_reply.id],
        )

    def test_review_and_reply_authors_link_to_public_profiles(self):
        response = self.client.get(self.detail_url)

        self.assertContains(
            response,
            f'href="{reverse("profile", kwargs={"username": self.first_author.username})}"',
        )
        self.assertContains(
            response,
            f'href="{reverse("profile", kwargs={"username": self.reply_author.username})}"',
        )

    def test_review_without_replies_has_no_reply_toggle(self):
        ReviewReply.objects.all().delete()

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<button class="review-replies-toggle"')

    def test_reply_prefetch_query_count_does_not_grow_with_reply_count(self):
        with CaptureQueriesContext(connection) as initial_queries:
            initial_response = self.client.get(self.detail_url)
        self.assertEqual(initial_response.status_code, 200)

        for index in range(6):
            author = get_user_model().objects.create_user(
                username=f"extra-reply-author-{index}",
                email=f"extra-reply-{index}@example.com",
            )
            ReviewReply.objects.create(
                review=self.first_review,
                user=author,
                text=f"Extra reply {index}",
            )

        with CaptureQueriesContext(connection) as populated_queries:
            populated_response = self.client.get(self.detail_url)
        self.assertEqual(populated_response.status_code, 200)
        self.assertLessEqual(len(populated_queries), len(initial_queries) + 1)

    def test_api_reply_is_displayed_in_open_thread_after_reload(self):
        self.client.force_login(self.reply_author)

        response = self.client.post(
            reverse("movies:review_reply_api", args=[self.first_review.id]),
            {"text": "A newly posted reply"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        detail_response = self.client.get(
            self.detail_url,
            {"replies": self.first_review.id},
        )
        self.assertContains(detail_response, 'aria-expanded="true"')
        self.assertContains(detail_response, f'id="review-replies-{self.first_review.id}"')
        self.assertContains(detail_response, "A newly posted reply")

    def test_both_pages_use_api_form_and_movie_return_url(self):
        self.client.force_login(self.reply_author)
        expected_url = (
            f"{self.detail_url}?replies={self.first_review.pk}"
            f"#review-{self.first_review.pk}"
        )
        detail = self.client.get(self.detail_url)
        feed = self.client.get(reverse("movies:show_reviews"))

        for response in (detail, feed):
            self.assertContains(response, 'data-review-reply-form')
            self.assertContains(response, f'action="{reverse("movies:review_reply_api", args=[self.first_review.pk])}"')
            self.assertContains(response, 'movies/js/review-replies.js')
            self.assertNotContains(response, f'/movies/review/{self.first_review.pk}/reply/')
        self.assertContains(detail, f'data-success-url="{expected_url}"')

    def test_guest_has_no_reply_form_on_either_page(self):
        for url in (self.detail_url, reverse("movies:show_reviews")):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'data-review-reply-form')
            self.assertNotContains(response, 'class="review-action-button review-reply-button"')

    def test_loaded_feed_cards_return_to_their_page_and_open_thread(self):
        self.client.force_login(self.reply_author)
        for index in range(10):
            movie = Movie.objects.create(name=f"Newer review movie {index}")
            Review.objects.create(user=self.first_author, movie=movie, rating=8, text=f"Newer review {index}")
        feed_url = reverse("movies:show_reviews")
        page = self.client.get(feed_url, {"page": 2, "format": "json"})
        self.assertEqual(page.status_code, 200)
        html = page.json()["html"]
        expected_url = f"{feed_url}?page=2&replies={self.first_review.pk}#review-{self.first_review.pk}"
        self.assertIn(f'data-success-url="{escape(expected_url)}"', html)
        self.assertIn(f'action="{reverse("movies:review_reply_api", args=[self.first_review.pk])}"', html)

        posted = self.client.post(
            reverse("movies:review_reply_api", args=[self.first_review.pk]),
            {"text": "Reply from loaded page"}, content_type="application/json",
        )
        self.assertEqual(posted.status_code, 201)
        reloaded = self.client.get(expected_url)
        self.assertEqual(reloaded.context["page_obj"].number, 2)
        self.assertContains(reloaded, 'aria-expanded="true"')
        self.assertContains(reloaded, "Reply from loaded page")

    def test_reply_text_is_escaped_on_both_pages(self):
        self.first_reply.text = '<script>alert("reply")</script>'
        self.first_reply.save()
        for url in (self.detail_url, reverse("movies:show_reviews")):
            response = self.client.get(url, {"replies": self.first_review.pk})
            self.assertContains(response, escape(self.first_reply.text))
            self.assertNotContains(response, self.first_reply.text)


class WatchStatusEndpointTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="library-owner",
            email="library-owner@example.com",
        )
        self.other_user = get_user_model().objects.create_user(
            username="other-library-owner",
            email="other-library-owner@example.com",
        )
        self.movie = Movie.objects.create(name="Library movie", year=2024)
        self.url = reverse("movies:set_movie_status")

    def post_status(self, user, status, **extra_payload):
        self.client.force_login(user)
        payload = {
            "movie_id": self.movie.id,
            "status": status,
            **extra_payload,
        }
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_repeating_status_removes_and_then_restores_it(self):
        WatchStatus.objects.create(
            user=self.owner,
            movie=self.movie,
            status=WatchStatus.StatusChoice.VIEWED,
        )

        remove_response = self.post_status(
            self.owner,
            WatchStatus.StatusChoice.VIEWED,
        )
        self.assertEqual(remove_response.status_code, 200)
        self.assertIsNone(remove_response.json()["status"])
        self.assertFalse(
            WatchStatus.objects.filter(user=self.owner, movie=self.movie).exists()
        )

        restore_response = self.post_status(
            self.owner,
            WatchStatus.StatusChoice.VIEWED,
        )
        self.assertEqual(restore_response.status_code, 200)
        self.assertEqual(
            restore_response.json()["status"],
            WatchStatus.StatusChoice.VIEWED,
        )
        self.assertTrue(
            WatchStatus.objects.filter(
                user=self.owner,
                movie=self.movie,
                status=WatchStatus.StatusChoice.VIEWED,
            ).exists()
        )

    def test_payload_cannot_change_another_users_status(self):
        other_status = WatchStatus.objects.create(
            user=self.other_user,
            movie=self.movie,
            status=WatchStatus.StatusChoice.DROPPED,
        )

        response = self.post_status(
            self.owner,
            WatchStatus.StatusChoice.VIEWED,
            user_id=self.other_user.id,
            username=self.other_user.username,
        )

        self.assertEqual(response.status_code, 200)
        other_status.refresh_from_db()
        self.assertEqual(other_status.status, WatchStatus.StatusChoice.DROPPED)
        self.assertTrue(
            WatchStatus.objects.filter(
                user=self.owner,
                movie=self.movie,
                status=WatchStatus.StatusChoice.VIEWED,
            ).exists()
        )


class ReviewDeletionPermissionTests(TestCase):
    def setUp(self):
        self.review_author = get_user_model().objects.create_user(
            username="delete-review-author",
            email="delete-review-author@example.com",
        )
        self.reply_author = get_user_model().objects.create_user(
            username="delete-reply-author",
            email="delete-reply-author@example.com",
        )
        self.outsider = get_user_model().objects.create_user(
            username="delete-outsider",
            email="delete-outsider@example.com",
        )
        self.superuser = get_user_model().objects.create_superuser(
            username="delete-admin",
            email="delete-admin@example.com",
            password="password123",
        )
        self.movie = Movie.objects.create(name="Deletion movie", year=2025)
        self.review = Review.objects.create(
            user=self.review_author,
            movie=self.movie,
            rating=8,
            text="Review to delete",
        )
        self.reply = ReviewReply.objects.create(
            review=self.review,
            user=self.reply_author,
            text="Reply to delete",
        )

    def test_reply_author_can_delete_own_reply(self):
        self.client.force_login(self.reply_author)
        detail_response = self.client.get(
            reverse("movies:detail", args=[self.movie.id])
        )
        delete_url = reverse("movies:delete_reply", args=[self.reply.id])
        self.assertContains(detail_response, f'action="{delete_url}"')

        response = self.client.post(delete_url)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ReviewReply.objects.filter(id=self.reply.id).exists())

    def test_other_user_cannot_delete_review_or_reply(self):
        self.client.force_login(self.outsider)

        reply_response = self.client.post(
            reverse("movies:delete_reply", args=[self.reply.id])
        )
        review_response = self.client.post(
            reverse("movies:delete_review", args=[self.review.id])
        )

        self.assertEqual(reply_response.status_code, 403)
        self.assertEqual(review_response.status_code, 403)
        self.assertTrue(ReviewReply.objects.filter(id=self.reply.id).exists())
        self.assertTrue(Review.objects.filter(id=self.review.id).exists())

    def test_superuser_can_delete_any_reply_and_review(self):
        self.client.force_login(self.superuser)
        detail_response = self.client.get(
            reverse("movies:detail", args=[self.movie.id])
        )
        reply_delete_url = reverse("movies:delete_reply", args=[self.reply.id])
        review_delete_url = reverse("movies:delete_review", args=[self.review.id])
        self.assertContains(detail_response, f'action="{reply_delete_url}"')
        self.assertContains(detail_response, f'action="{review_delete_url}"')

        reply_response = self.client.post(reply_delete_url)
        review_response = self.client.post(review_delete_url)

        self.assertEqual(reply_response.status_code, 302)
        self.assertEqual(review_response.status_code, 302)
        self.assertFalse(ReviewReply.objects.filter(id=self.reply.id).exists())
        self.assertFalse(Review.objects.filter(id=self.review.id).exists())
