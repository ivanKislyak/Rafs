"""Give every existing user the private "Liked Titles" (Favourite) playlist.

New users get it from the post_save signal in movies/signals.py; this covers
accounts created before that. Favourite playlists are always private, so any
that were made public are switched back.
"""
from django.conf import settings
from django.db import migrations

LIKED_TITLES_NAME = "Liked Titles"
FAVOURITE = "FAVOURITE"


def create_liked_titles(apps, schema_editor):
    User = apps.get_model(settings.AUTH_USER_MODEL)
    Playlist = apps.get_model("movies", "Playlist")

    Playlist.objects.filter(kind=FAVOURITE, is_public=True).update(is_public=False)

    owners_with_favourite = Playlist.objects.filter(kind=FAVOURITE).values("owner_id")
    missing = User.objects.exclude(pk__in=owners_with_favourite).values_list("pk", flat=True)
    Playlist.objects.bulk_create(
        (
            Playlist(owner_id=user_id, name=LIKED_TITLES_NAME, kind=FAVOURITE, is_public=False)
            for user_id in missing.iterator()
        ),
        batch_size=500,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("movies", "0054_alter_playlistitem_added_at"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Reversing keeps the playlists: they may already hold the users' liked movies.
        migrations.RunPython(create_liked_titles, migrations.RunPython.noop),
    ]
