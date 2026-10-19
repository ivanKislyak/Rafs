from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Count

from movies.models import GlobalSearchIndex
from movies.services import search_index


class Command(BaseCommand):
    help = (
        "Rebuild all five GlobalSearchIndex document types using PostgreSQL. "
        "Source records are preserved; indexing remains manual."
    )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            raise CommandError("rebuild_search_index requires PostgreSQL.")

        try:
            with transaction.atomic():
                previous_count = GlobalSearchIndex.objects.count()
                GlobalSearchIndex.objects.all().delete()

                search_index.index_new_movies()
                search_index.index_new_reviews()
                search_index.index_new_users()
                search_index.index_new_persons()
                search_index.index_new_studios()

                counts = {
                    row["content_type__model"]: row["total"]
                    for row in GlobalSearchIndex.objects.values(
                        "content_type__model"
                    ).annotate(total=Count("pk"))
                }
        except Exception as exc:
            raise CommandError(
                f"Search index rebuild failed; previous index was preserved: {exc}"
            ) from exc

        total = sum(counts.values())
        self.stdout.write(self.style.SUCCESS(
            f"Search index rebuilt: {previous_count} previous documents, {total} current. "
            f"Movies: {counts.get('movie', 0)}; reviews: {counts.get('review', 0)}; "
            f"users: {counts.get('user', 0)}; persons: {counts.get('person', 0)}; "
            f"studios: {counts.get('studio', 0)}."
        ))
