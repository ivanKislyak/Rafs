import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from celery import Celery

app = Celery("rafs")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()