"""Small selection extension of the animation campaign runner (AI assisted).

The runner's HTTP, exact identity, fill-only save, locks and date partitioning
remain shared. These commands have distinct SQLite manifests, never animation's.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError

from movies.management.commands.import_animation import CandidateIssue, Command as AnimationCommand
from movies.management.commands.import_popular_movies import IMDB, claim_qids, claim_values, clean, find_existing
from movies.services.animation_state import AnimationState, SCHEMA_VERSION, saved_config

COUNTRIES = ("RU", "UA", "KZ")
VERSIONS = {("series-v1", SCHEMA_VERSION), ("country-movies-v1", SCHEMA_VERSION)}


def catalogue_config(directory):
    return saved_config(directory, versions=VERSIONS, command="series/country_movies")


def selected_countries(value):
    requested = {code.strip().upper() for code in value.split(",") if code.strip()}
    if not requested or requested - set(COUNTRIES):
        raise CommandError("--countries must contain RU, UA and/or KZ, separated by commas.")
    return [code for code in COUNTRIES if code in requested]


class CatalogueState(AnimationState):
    read_config = staticmethod(catalogue_config)

    def __init__(self, directory, config):
        previous = self.read_config(directory)
        if previous is not None and previous != config:
            raise CommandError("State-dir belongs to another database or selection; use a separate directory.")
        self.importer = config["importer"]
        super().__init__(directory, config)

    def initial_partitions(self, config):
        # origin_country is only a priority hint, NOT production country proof.
        # A broad movie pass follows, to also find co-productions omitted by it.
        for country in config.get("countries", []):
            yield "movie", "origin-" + country, "", ""
        yield from super().initial_partitions(config)


class CatalogueCommand(AnimationCommand):
    read_config = staticmethod(catalogue_config)
    state_class = CatalogueState

    def add_arguments(self, parser):
        parser.set_defaults(media_type=self.media_type, exclude_anime=False)
        parser.add_argument("--target-new", type=int, default=0, help="Optional SQLite-recorded new-card goal; 0 (default) scans all available partitions. No 15000 ceiling.")
        parser.add_argument("--max-candidates", type=int, default=0, help="Checks in this invocation, including skips; 0 = unlimited. Resume permits another budget.")
        parser.add_argument("--min-votes", type=int, default=0)
        parser.add_argument("--languages", default="en,ru,uk,kk,es,de")
        parser.add_argument("--sort", choices=["popularity.desc", "vote_count.desc"], default="popularity.desc")
        parser.add_argument("--date-from", help="Inclusive dated-discovery bound; default 0001-01-01, saved in SQLite.")
        parser.add_argument("--date-to", help="Inclusive dated-discovery bound; default 9999-12-31, saved in SQLite.")
        parser.add_argument("--state-dir", help="Separate state/cache/reports; selection-specific default under .rafs_import.")
        parser.add_argument("--dry-run", action="store_true", help="No Django writes or indexing. Local discovery/cache/report only.")
        parser.add_argument("--retry-skipped", action="store_true")
        parser.add_argument("--refresh-cache", action="store_true")
        parser.add_argument("--tmdb-delay", type=float, default=0.6)
        parser.add_argument("--wikidata-delay", type=float, default=1.0)
        parser.add_argument("--sparql-delay", type=float, default=5.0)
        parser.add_argument("--maxlag-wait", type=int, default=1800)

    def handle(self, *args, **options):
        options["media_type"], options["exclude_anime"] = self.media_type, False
        if self.media_type == "movie":
            options["country_codes"] = selected_countries(options["countries"])
        if not options["state_dir"]:
            directory = Path(settings.BASE_DIR) / ".rafs_import" / self.campaign_label
            if self.media_type == "movie":
                directory /= "-".join(options["country_codes"])
            options["state_dir"] = str(directory)
        return super().handle(*args, **options)

    def validate_target(self, target):
        if target < 0:
            raise CommandError("--target-new cannot be negative; use 0 for all available partitions.")

    def target_reached(self):
        return bool(self.options["target_new"] and super().target_reached())

    def selection_config(self, options):
        return {"genre": None, "exclude_anime": False, "countries": options.get("country_codes", [])}

    def selection_parameters(self, part):
        if part["mode"].startswith("origin-"):
            # One ISO code per request. Multi-country OR support is not assumed.
            return {"with_origin_country": part["mode"].removeprefix("origin-")}
        return {}

    def validate_item(self, item, row):
        if not item:
            raise CandidateIssue("missing_details", "TMDB details is missing.")
        if type(item.get("id")) is not int or item["id"] != row["tmdb_id"]:
            raise CommandError("Unexpected TMDB details ID; campaign stopped.")
        if item.get("adult") or item.get("video"):
            raise CandidateIssue("adult_video", "TMDB marks this record adult/video.")
        if (item.get("vote_count") or 0) < self.config["min_votes"]:
            raise CandidateIssue("min_votes", "Below --min-votes.")
        if self.config["countries"] and not set(self.config["countries"]) & self.production_countries(item):
            raise CandidateIssue("outside_countries", "No selected production country in TMDB details (original language/origin country are not proof).")

    @staticmethod
    def production_countries(item):
        payload = item.get("production_countries")
        if not isinstance(payload, list) or any(not isinstance(country, dict) for country in payload):
            raise CandidateIssue("missing_production_countries", "TMDB production_countries is unavailable; cannot verify selection.")
        return {country.get("iso_3166_1") for country in payload if country.get("iso_3166_1")}

    def validate_relations(self, row, item, qid, entity, related):
        if not self.config["countries"]:
            return
        production = self.production_countries(item)
        imdb = clean(item.get("external_ids", {}).get("imdb_id") or item.get("imdb_id"))
        if not imdb:
            imdbs = [value for value in claim_values(entity, "P345") if isinstance(value, str) and IMDB.fullmatch(value)]
            imdb = next(iter(imdbs), "")
        existing = find_existing(entity["id"], qid, imdb, set(), None)
        country_ids = set(claim_qids(entity, ("P495",)))
        if existing:
            country_ids.update(existing.countries.values_list("wikidata_id", flat=True))
        if not country_ids:
            return  # TMDB proves selection; absent P495 does not invent a relation.
        countries = self.api.entities(sorted(country_ids), claims=True)
        related.update(countries)
        for country_id in sorted(country_ids):
            data = countries.get(country_id, {})
            codes = {clean(value).upper() for value in claim_values(data, "P297")}
            if not codes:
                raise CandidateIssue("unverified_country", f"Cannot compare Wikidata/manual country {country_id}: no ISO P297.")
            if not codes <= production:
                raise CandidateIssue("country_conflict", f"Wikidata/manual country {country_id} ({','.join(sorted(codes))}) contradicts TMDB production countries ({','.join(sorted(production))}). No data changed.")

    def snapshot(self, status):
        summary = super().snapshot(status)
        if not self.options["target_new"]:
            summary.update(target_new=None, shortfall=None)
        return summary

    def run_campaign(self):
        status = super().run_campaign()
        if status == "source_exhausted" and self.state.statistics()["coverage_limited_partitions"]:
            return "available_partitions_exhausted"
        return status
