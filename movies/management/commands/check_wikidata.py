from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from movies.tasks import check_wikidata_movie
import re

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("qid")

    def handle(self, *args, **options):
        qid = options["qid"]
        pattern = r"Q[0-9]+"
        if re.fullmatch(pattern, qid) is None:
            raise CommandError('Expected a Wikidata ID like Q123')
        if not settings.CELERY_BROKER_URL:
            raise CommandError("Set CELERY_BROKER_URL before queuing a task")
        job = check_wikidata_movie.delay(qid)
        self.stdout.write(f"Queued task {job.id}")