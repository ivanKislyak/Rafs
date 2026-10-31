"""Broad whole-series import. Written with AI assistance (OpenAI Codex)."""
from movies.services.catalogue_import import CatalogueCommand


class Command(CatalogueCommand):
    media_type = "tv"
    importer = "series-v1"
    campaign_label = "series"
    help = "Import whole TV/mini-series of all countries/genres/platforms, including animation/anime. No provider or Scripted filter. Default: scan all available partitions. Written with AI assistance (OpenAI Codex). See README_import_series.md."
