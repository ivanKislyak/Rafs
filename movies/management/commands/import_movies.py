import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from movies.models import Movie

class Command(BaseCommand):
    help = "Imports movies from a JSON file"


    def handle(self, *args, **options):
        json_path = settings.BASE_DIR / "movies" / "movies.json"

        self.stdout.write(str(json_path))

        if not json_path.exists():
            raise CommandError("Файл отсутствует")

        with json_path.open(encoding="utf-8") as file:
            movies_data = json.load(file)
            self.stdout.write(f"Тип {type(movies_data)}")
            self.stdout.write(f"Количество фильмов в json: {len(movies_data)}")

        created_count = 0
        updated_count = 0

        for movie_data in movies_data:
            self.stdout.write("\n")
            movie, created = Movie.objects.update_or_create(name=movie_data["name"], year=movie_data["year"],
                                                            defaults={"rate": movie_data["rate"], "description": movie_data["description"],
                                                                      "path": movie_data.get("path") or ""}
                                                            )
            if created:
                created_count += 1
            else:
                updated_count += 1

            self.stdout.write(str(movie.pk))
            self.stdout.write(str(movie.name))
            self.stdout.write(str(created))

        self.stdout.write("\n")
        self.stdout.write(f"Количество фильмов в БД после цикла: {Movie.objects.count()}")
        self.stdout.write(f"Созданные записи: {created_count}")
        self.stdout.write(f"Обновленные записи: {updated_count}")
