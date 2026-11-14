"""Shrink stored avatars and movie covers to 2x their largest display size.

Originals are copied to --backup-dir first (media/ is not in git). Files the
re-encode would not shrink by 10%+ are left alone. Renamed files (e.g.
avatar .png -> .webp) are updated in the database before the old file is removed.
"""
import shutil
from pathlib import Path, PurePosixPath

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image, UnidentifiedImageError

from core.images import AVATAR_SIZE, MOVIE_COVER_SIZE, encode_jpeg, encode_webp
from movies.models import Movie


class Command(BaseCommand):
    help = "Downscale and lossy-encode stored avatars and movie covers."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--backup-dir", help="Where to copy originals before rewriting them.")

    def handle(self, *args, dry_run=False, backup_dir=None, **options):
        if not dry_run and not backup_dir:
            raise CommandError("Pass --backup-dir (originals are not recoverable otherwise) or --dry-run.")
        self.dry_run = dry_run
        self.backup_dir = Path(backup_dir) if backup_dir else None
        self.saved = 0

        jobs = [
            (get_user_model().objects.exclude(avatar_image=""), "avatar_image", encode_webp, AVATAR_SIZE, ".webp"),
            (Movie.objects.exclude(cover=""), "cover", encode_jpeg, MOVIE_COVER_SIZE, ".jpg"),
        ]
        for queryset, field, encode, box, suffix in jobs:
            for obj in queryset.exclude(**{f"{field}__isnull": True}).iterator():
                self.process(obj, field, encode, box, suffix)

        verb = "Would save" if dry_run else "Saved"
        self.stdout.write(self.style.SUCCESS(f"{verb} {self.saved / 1024 / 1024:.1f} MB"))

    def process(self, obj, field, encode, box, suffix):
        file = getattr(obj, field)
        storage, name = file.storage, file.name
        if not storage.exists(name):
            self.stdout.write(f"skip missing {name}")
            return
        before = storage.size(name)
        try:
            with storage.open(name, "rb") as handle, Image.open(handle) as source:
                size = source.size
                data = encode(source, box)
        except (UnidentifiedImageError, OSError, ValueError) as error:
            self.stderr.write(f"skip unreadable {name}: {error}")
            return
        if len(data) > before * 0.9:  # Not worth another lossy generation.
            self.stdout.write(f"keep {name} ({before // 1024} KB, already small)")
            return

        self.saved += before - len(data)
        self.stdout.write(f"{name}: {size[0]}x{size[1]} {before // 1024} KB -> {len(data) // 1024} KB")
        if self.dry_run:
            return

        target = self.backup_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with storage.open(name, "rb") as handle, open(target, "wb") as out:
            shutil.copyfileobj(handle, out)

        new_name = str(PurePosixPath(name).with_suffix(suffix))
        if new_name == name:
            storage.delete(name)
            stored = storage.save(name, ContentFile(data))
            if stored != name:  # Storage picked another name; keep the DB in step.
                type(obj).objects.filter(pk=obj.pk).update(**{field: stored})
            return

        stored = storage.save(new_name, ContentFile(data))
        try:
            with transaction.atomic():
                type(obj).objects.filter(pk=obj.pk).update(**{field: stored})
        except Exception:
            storage.delete(stored)
            raise
        storage.delete(name)
