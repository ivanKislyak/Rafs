"""Rebuild checks use the isolated Django test database and no external APIs."""

from io import StringIO
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.search import SearchQuery
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection
from django.test import SimpleTestCase, TestCase

from accounts.models import User
from movies.models import GlobalSearchIndex, Movie, Review
from movies.movie_models import Person, Studio


class RebuildDatabaseSupportTests(SimpleTestCase):
    def test_unsupported_database_fails_before_indexing(self):
        with patch("movies.management.commands.rebuild_search_index.connection") as database, patch(
            "movies.services.search_index.index_new_movies"
        ) as index_movies:
            database.vendor = "sqlite"
            with self.assertRaisesMessage(CommandError, "requires PostgreSQL"):
                call_command("rebuild_search_index", stdout=StringIO())
            index_movies.assert_not_called()


@skipUnless(connection.vendor == "postgresql", "Full-text rebuild requires PostgreSQL")
class RebuildSearchIndexTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="previoususer", email="index@example.com")
        cls.movie = Movie.objects.create(name="previousmovie")
        cls.movie.set_current_language("en")
        cls.movie.wikidata_name = "previousmovie"
        cls.movie.save()
        cls.review = Review.objects.create(
            user=cls.user, movie=cls.movie, rating=8, text="previousreview",
        )
        cls.person = Person.objects.create(
            wikidata_id="CHECK_PERSON", _current_language="en", name="previousperson",
        )
        cls.studio = Studio.objects.create(
            wikidata_id="CHECK_STUDIO", _current_language="en", name="previousstudio",
        )
        for index, flags in enumerate([{"is_active": False}, {"is_deleted": True}]):
            user = User.objects.create_user(
                username=f"excludeduser{index}", email=f"excluded{index}@example.com", **flags,
            )
            Review.objects.create(user=user, movie=cls.movie, rating=7, text="Excluded review")
        for text in ["", " \t\n "]:
            movie = Movie.objects.create(name="Empty review movie")
            Review.objects.create(user=cls.user, movie=movie, rating=7, text=text)

    def rebuild(self):
        output = StringIO()
        call_command("rebuild_search_index", stdout=output)
        return output.getvalue()

    @staticmethod
    def source_snapshot():
        models = [User, Movie, Review, Person, Studio]
        models += [model._parler_meta.root_model for model in [Movie, Person, Studio]]
        return {model._meta.label: list(model.objects.order_by("pk").values()) for model in models}

    @staticmethod
    def document(instance):
        return GlobalSearchIndex.objects.filter(
            content_type=ContentType.objects.get_for_model(instance), object_id=instance.pk,
        )

    def test_initial_build_includes_all_five_types_and_only_eligible_records(self):
        before = self.source_snapshot()
        output = self.rebuild()
        expected = {
            (ContentType.objects.get_for_model(instance).pk, instance.pk)
            for instance in [*Movie.objects.all(), self.review, self.user, self.person, self.studio]
        }
        self.assertEqual(
            set(GlobalSearchIndex.objects.values_list("content_type_id", "object_id")), expected,
        )
        self.assertIn("7 current", output)
        self.assertIn("Movies: 3; reviews: 1; users: 1; persons: 1; studios: 1", output)
        self.assertEqual(self.source_snapshot(), before)

    def test_repeated_build_produces_same_documents_without_duplicates(self):
        self.rebuild()
        fields = ["content_type_id", "object_id", "search_vector"]
        before = list(GlobalSearchIndex.objects.order_by(*fields[:2]).values_list(*fields))
        self.rebuild()
        self.assertEqual(
            list(GlobalSearchIndex.objects.order_by(*fields[:2]).values_list(*fields)), before,
        )

    def test_changed_documents_are_rebuilt_for_every_type(self):
        self.rebuild()
        self.movie.name = self.movie.wikidata_name = "quasar"
        self.movie.save()
        self.review.text = "telescope"
        self.review.save()
        self.user.username = "novauser"
        self.user.save()
        self.person.name = "orion"
        self.person.save()
        self.studio.name = "compass"
        self.studio.save()
        sources = self.source_snapshot()

        self.rebuild()

        for instance, new_term, old_term in [
            (self.movie, "quasar", "previousmovie"),
            (self.review, "telescope", "previousreview"),
            (self.user, "novauser", "previoususer"),
            (self.person, "orion", "previousperson"),
            (self.studio, "compass", "previousstudio"),
        ]:
            with self.subTest(model=instance._meta.label):
                self.assertTrue(self.document(instance).filter(
                    search_vector=SearchQuery(new_term, config="english"),
                ).exists())
                self.assertFalse(self.document(instance).filter(
                    search_vector=SearchQuery(old_term, config="english"),
                ).exists())
        self.assertEqual(self.source_snapshot(), sources)

    def test_orphaned_document_is_removed(self):
        obsolete = Movie.objects.create(name="Obsolete movie")
        self.rebuild()
        document_pk = self.document(obsolete).get().pk
        obsolete.delete()
        self.assertTrue(GlobalSearchIndex.objects.filter(pk=document_pk).exists())

        self.rebuild()

        self.assertFalse(GlobalSearchIndex.objects.filter(pk=document_pk).exists())
        self.assertEqual(GlobalSearchIndex.objects.count(), 7)

    def test_newly_ineligible_users_and_reviews_are_removed(self):
        self.rebuild()
        self.user.is_active = False
        self.user.save()
        self.rebuild()
        self.assertFalse(self.document(self.user).exists())
        self.assertFalse(self.document(self.review).exists())

    def test_newly_empty_review_is_removed(self):
        self.rebuild()
        self.review.text = " \t\n "
        self.review.save()
        self.rebuild()
        self.assertFalse(self.document(self.review).exists())
        self.assertTrue(self.document(self.user).exists())

    def test_failure_restores_exact_previous_index_after_partial_build(self):
        self.rebuild()
        before = list(GlobalSearchIndex.objects.order_by("pk").values())
        self.movie.name = self.movie.wikidata_name = "changed before failed rebuild"
        self.movie.save()
        sources = self.source_snapshot()

        for error in [RuntimeError("fixture failure"), DatabaseError("fixture database failure")]:
            with self.subTest(error=type(error).__name__), patch(
                "movies.services.search_index.index_new_users", side_effect=error,
            ):
                output = StringIO()
                with self.assertRaisesMessage(CommandError, "previous index was preserved"):
                    call_command("rebuild_search_index", stdout=output)
                self.assertEqual(output.getvalue(), "")
                self.assertEqual(list(GlobalSearchIndex.objects.order_by("pk").values()), before)
                self.assertEqual(self.source_snapshot(), sources)
