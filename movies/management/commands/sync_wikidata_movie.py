from django.core.management.base import BaseCommand, CommandError
from movies.services.wikidata import fetch_movie_raw, parse_movie_data
from movies.models import Movie

class Command(BaseCommand):
    help = "Fetch and update movie data from Wikidata by its ID"

    def add_arguments(self, parser):
        parser.add_argument('wikidata_id', type=str)

    def handle(self, *args, **options):
        wikidata_id = options['wikidata_id']
        result = parse_movie_data(fetch_movie_raw(wikidata_id))
        obj, created = Movie.objects.update_or_create(
            wikidata_id=wikidata_id,
            defaults={
                'wikidata_name': result['wikidata_name'],
                'wikidata_description': result['wikidata_description']
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f'Создан новый объект: {obj.wikidata_id}'))
        else:
            self.stdout.write(self.style.WARNING(f'Обновлен существующий объект: {obj.wikidata_id}'))