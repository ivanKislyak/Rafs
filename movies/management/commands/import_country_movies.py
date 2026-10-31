"""Production-country movie import. Written with AI assistance (OpenAI Codex)."""
from movies.services.catalogue_import import CatalogueCommand


class Command(CatalogueCommand):
    media_type = "movie"
    importer = "country-movies-v1"
    campaign_label = "country_movies"
    help = "Import movies produced in any selected RU/UA/KZ country (OR), including animation. Origin-country priority passes followed by a broad scan; production_countries is rechecked in details. Written with AI assistance (OpenAI Codex). See README_import_country_movies.md."

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--countries", default="RU,UA,KZ", help="Production-country OR selection: RU,UA,KZ; co-productions included. USSR is not mapped to successors.")
