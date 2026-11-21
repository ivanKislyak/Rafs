"""Keep playlist search documents in step with the playlist itself,
and give every new user the private Liked Titles playlist.

Other document types are refreshed by ``rebuild_search_index`` only; playlists
also sync immediately because visibility changes must take effect at once.
The search API additionally filters by ``searchable_playlists()``, so privacy
does not depend on these handlers running.
"""
from django.conf import settings
from django.db import connection
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Playlist
from .services.liked_titles import ensure_liked_titles
from .services.search_index import refresh_playlist_document, remove_playlist_document


def _full_text_available():
    return connection.vendor == "postgresql"


@receiver(post_save, sender=Playlist, dispatch_uid="playlist_search_document_sync")
def sync_playlist_search_document(sender, instance, raw=False, **kwargs):
    if raw or not _full_text_available():
        return
    refresh_playlist_document(instance.pk)


@receiver(post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="create_liked_titles_playlist")
def create_liked_titles_playlist(sender, instance, created, raw=False, **kwargs):
    # Every new user gets the private Liked Titles playlist the heart buttons add to.
    # Fixture loading (raw) is skipped: fixtures carry their own playlists.
    if created and not raw:
        ensure_liked_titles(instance)


@receiver(post_delete, sender=Playlist, dispatch_uid="playlist_search_document_delete")
def delete_playlist_search_document(sender, instance, **kwargs):
    # GlobalSearchIndex uses a generic relation, so nothing cascades on its own.
    remove_playlist_document(instance.pk)
