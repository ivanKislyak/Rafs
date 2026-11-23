from django.db import migrations

BATCH_SIZE = 500


def forwards(apps, schema_editor):
    PlaylistItem = apps.get_model("movies", "PlaylistItem")
    batch = []
    current_playlist = None
    number = 0

    items = PlaylistItem.objects.order_by("playlist_id", "position", "added_at", "pk")
    for item in items.iterator():
        if item.playlist_id != current_playlist:
            current_playlist = item.playlist_id
            number = 0
        number += 1
        if item.position != number:
            item.position = number
            batch.append(item)
            if len(batch) >= BATCH_SIZE:
                PlaylistItem.objects.bulk_update(batch, ["position"])
                batch = []
    if batch:
        PlaylistItem.objects.bulk_update(batch, ["position"])


class Migration(migrations.Migration):

    dependencies = [
        ("movies", "0058_playlist_external_id_required"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]