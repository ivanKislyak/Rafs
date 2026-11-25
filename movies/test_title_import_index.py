"""Search indexing after a staff import: after commit, PostgreSQL only, never breaking the import."""

from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import SUCCESS, WARNING, get_messages
from django.contrib.postgres.search import SearchQuery
from django.db import connection
from django.core.cache import cache
from django.test import TransactionTestCase
from django.urls import reverse

from movies.models import GlobalSearchIndex, Movie
from movies.movie_models import Person, Studio
from movies.services import title_import
from movies.services.title_import import import_tmdb
from movies.test_title_import import FreshCacheTestCase, matrix_api

MODULE = "movies.services.title_import"


class IndexScheduleTests(FreshCacheTestCase):
    def test_indexes_the_title_then_new_people_and_studios_after_commit(self):
        order = []
        with patch(f"{MODULE}.search_index_supported", return_value=True), \
                patch(f"{MODULE}.refresh_movie_documents", side_effect=lambda ids: order.append(("movie", ids))), \
                patch(f"{MODULE}.index_new_persons", side_effect=lambda: order.append(("persons",))), \
                patch(f"{MODULE}.index_new_studios", side_effect=lambda: order.append(("studios",))):
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                result = import_tmdb("movie", 603, api=matrix_api())
            self.assertEqual(order, [], "Indexing must wait for the commit")
            self.assertEqual(len(callbacks), 1)
            callbacks[0]()
        self.assertEqual(order, [("movie", [result.movie.pk]), ("persons",), ("studios",)])
        self.assertEqual(result.warnings, [])

    def test_no_indexing_on_sqlite(self):
        with patch(f"{MODULE}.search_index_supported", return_value=False), \
                patch(f"{MODULE}.refresh_movie_documents") as refresh:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                import_tmdb("movie", 603, api=matrix_api())
        self.assertEqual(callbacks, [])
        refresh.assert_not_called()

    def test_vendor_check_follows_the_connection(self):
        self.assertEqual(title_import.search_index_supported(), connection.vendor == "postgresql")

    def test_index_failure_keeps_the_title_and_warns(self):
        with patch(f"{MODULE}.search_index_supported", return_value=True), \
                patch(f"{MODULE}.refresh_movie_documents", side_effect=RuntimeError("index down")), \
                patch(f"{MODULE}.index_new_persons") as persons, \
                self.assertLogs(MODULE, "ERROR") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                result = import_tmdb("movie", 603, api=matrix_api())
        self.assertTrue(Movie.objects.filter(pk=result.movie.pk).exists())
        self.assertEqual(result.warnings, [title_import.INDEX_WARNING])
        self.assertIn("Search indexing failed", logs.output[0])
        persons.assert_not_called()

    def test_rejected_import_schedules_nothing(self):
        Movie.objects.create(wikidata_id="Q999", imdb_id="tt0133093", name="Other record")
        with patch(f"{MODULE}.search_index_supported", return_value=True), \
                patch(f"{MODULE}.refresh_movie_documents") as refresh:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with self.assertRaises(title_import.StaffImportError):
                    import_tmdb("movie", 603, api=matrix_api())
        self.assertEqual(callbacks, [])
        refresh.assert_not_called()


class IndexWarningViewTests(TransactionTestCase):
    """Real commits, so on_commit runs before the view answers, as in production."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

    def test_staff_sees_a_warning_when_indexing_fails(self):
        staff = get_user_model().objects.create_user(username="editor", email="editor@example.com", is_staff=True)
        self.client.force_login(staff)
        with patch(f"{MODULE}.WebAPI.from_settings", return_value=matrix_api()), \
                patch(f"{MODULE}.search_index_supported", return_value=True), \
                patch(f"{MODULE}.refresh_movie_documents", side_effect=RuntimeError("index down")), \
                self.assertLogs(MODULE, "ERROR"):
            response = self.client.post(reverse("movies:tmdb_import_item"), {"media_type": "movie", "tmdb_id": "603"})
        movie = Movie.objects.get()
        self.assertRedirects(response, reverse("movies:detail", args=[movie.pk]), fetch_redirect_response=False)
        levels = [m.level for m in get_messages(response.wsgi_request)]
        self.assertEqual(levels, [SUCCESS, WARNING])


@skipUnless(connection.vendor == "postgresql", "Full-text documents require PostgreSQL")
class PostgresIndexTests(FreshCacheTestCase):
    def test_imported_title_people_and_studio_are_searchable(self):
        with self.captureOnCommitCallbacks(execute=True):
            result = import_tmdb("movie", 603, api=matrix_api())
        self.assertEqual(result.warnings, [])

        def document(model, pk):
            return GlobalSearchIndex.objects.filter(content_type=ContentType.objects.get_for_model(model), object_id=pk)

        movie_doc = document(Movie, result.movie.pk)
        self.assertEqual(movie_doc.get().tmdb_popularity, 88.5)
        for text, config in (("Matrix", "english"), ("Матрица", "russian"), ("Keanu", "english")):
            self.assertTrue(movie_doc.filter(search_vector=SearchQuery(text, config=config)).exists(), text)
        actor = Person.objects.get(wikidata_id="Q500")
        self.assertTrue(document(Person, actor.pk).filter(search_vector=SearchQuery("Reeves", config="english")).exists())
        studio = Studio.objects.get(wikidata_id="Q400")
        self.assertTrue(document(Studio, studio.pk).exists())

    def test_repeated_import_replaces_the_document_instead_of_adding_one(self):
        for _ in range(2):
            with self.captureOnCommitCallbacks(execute=True):
                result = import_tmdb("movie", 603, api=matrix_api())
        content_type = ContentType.objects.get_for_model(Movie)
        self.assertEqual(GlobalSearchIndex.objects.filter(content_type=content_type, object_id=result.movie.pk).count(), 1)
