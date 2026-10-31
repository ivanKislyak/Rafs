import logging

from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.search import SearchVector
from django.db import transaction
from django.db.models import Prefetch, Value

from accounts.models import User
from movies.models import GlobalSearchIndex, Movie, Review
from movies.movie_models import Country, Genre, Person, Studio, TypeOfWork


BATCH_SIZE = 1000
ENGLISH_TRANSLATIONS_ATTR = "_search_english_translations"
RUSSIAN_TRANSLATIONS_ATTR = "_search_russian_translations"
SPANISH_TRANSLATION_ATTR = "_search_spanish_translations"
GERMAN_TRANSLATION_ATTR = "_search_german_translations"

prefetch_trans_attr = [
    ENGLISH_TRANSLATIONS_ATTR, RUSSIAN_TRANSLATIONS_ATTR, 
    SPANISH_TRANSLATION_ATTR, GERMAN_TRANSLATION_ATTR,
    "_search_ukrainian_translations", "_search_kazakh_translations"]
prefetch_lang_code = ["en", "ru", "es", "de", "uk", "kk"]
# PostgreSQL has no built-in Ukrainian/Kazakh stemmers. Their literal tokens
# remain searchable through RAFS's existing query configurations.
prefetch_languages = ["english", "russian", "spanish", "german", "simple", "simple"]

logger = logging.getLogger(__name__)

# Auxiliary functions
def _clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _join_unique(values):
    unique_values = []
    seen = set()

    for value in values:
        text = _clean_text(value)
        key = text.casefold()
        if not text or key in seen:
            continue

        seen.add(key)
        unique_values.append(text)

    return " ".join(unique_values)


def _translation_prefetch(lookup, model, trans_attr: str, lang_code: str):
    translation_model = model._parler_meta.root_model
    translations = translation_model.objects.filter(language_code=lang_code)
    return Prefetch(
        lookup,
        queryset=translations,
        to_attr=trans_attr,
    )


def _lang_value(instance, field_name, trans_attr: str):
    translations = getattr(instance, trans_attr, ())
    if not translations:
        return ""
    return _clean_text(getattr(translations[0], field_name, ""))


def _lang_named_queryset(model, trans_attr: str, lang_code: str):
    return model.objects.only("pk", "wikidata_id").prefetch_related(
        _translation_prefetch("translations", model, trans_attr, lang_code=lang_code)
    )


def _build_search_vector(text_a="", text_b="", text_c="", text_d="", config_lang="english"):
    return (
        SearchVector(Value(text_a), weight="A", config=config_lang)
        + SearchVector(Value(text_b), weight="B", config=config_lang)
        + SearchVector(Value(text_c), weight="C", config=config_lang)
        + SearchVector(Value(text_d), weight="D", config=config_lang)
    )

# Global Prefetch
global_prefetch = []

for attr, lang_code in zip(prefetch_trans_attr, prefetch_lang_code):
    sfx = f"_{lang_code}"

    global_prefetch.extend(
        [
            _translation_prefetch("translations", Movie, attr, lang_code=lang_code),
            _translation_prefetch("type_of_work__translations", TypeOfWork, attr, lang_code=lang_code
            ),
            Prefetch(
                "genres",
                queryset=_lang_named_queryset(Genre, attr, lang_code=lang_code),
                to_attr=f"_search_genres{sfx}",
            ),
            Prefetch(
                "actors",
                queryset=_lang_named_queryset(Person, attr, lang_code=lang_code),
                to_attr=f"_search_actors{sfx}",
            ),
            Prefetch(
                "countries",
                queryset=_lang_named_queryset(Country, attr, lang_code=lang_code),
                to_attr=f"_search_countries{sfx}",
            ),
            Prefetch(
                "studio",
                queryset=_lang_named_queryset(Studio, attr, lang_code=lang_code),
                to_attr=f"_search_studios{sfx}",
            ),
            Prefetch(
                "director",
                queryset=_lang_named_queryset(Person, attr, lang_code=lang_code),
                to_attr=f"_search_directors{sfx}",
            ),
            Prefetch(
                "screenwriter",
                queryset=_lang_named_queryset(Person, attr, lang_code=lang_code),
                to_attr=f"_search_screenwriters{sfx}",
            ),
            Prefetch(
                "producer",
                queryset=_lang_named_queryset(Person, attr, lang_code=lang_code),
                to_attr=f"_search_producers{sfx}",
            ),
            Prefetch(
                "composer",
                queryset=_lang_named_queryset(Person, attr, lang_code=lang_code),
                to_attr=f"_search_composers{sfx}")
        ]
    )

# Main Functions
def index_new_movies(movie_ids=None):
    content_type = ContentType.objects.get_for_model(Movie)
    indexed_object_ids = GlobalSearchIndex.objects.filter(
        content_type=content_type
    ).values_list("object_id", flat=True)

    movies = (
        Movie.objects.exclude(pk__in=indexed_object_ids)
        .select_related("type_of_work")
        .only(
            "pk",
            "wikidata_id",
            "imdb_id",
            "year",
            "type_of_work_id",
            "name",
            "description",
        )
        .prefetch_related(
            # prefetching on all languages
            *global_prefetch,
            "tags"
        )
    )
    if movie_ids is not None:
        movies = movies.filter(pk__in=movie_ids)

    documents = []
    prepared_count = 0

    for movie in movies.iterator(chunk_size=BATCH_SIZE):
        combined_vector = None
        
        for attr, language, lang_code in zip(prefetch_trans_attr, prefetch_languages, prefetch_lang_code):
            type_of_work_name = ""
            if movie.type_of_work is not None:
                type_of_work_name = _lang_value(movie.type_of_work, "name", trans_attr=attr)

            names = _join_unique(
                [_lang_value(movie, "wikidata_name", trans_attr=attr), movie.name if lang_code not in {"uk", "kk"} else ""]
            )
            descriptions = _join_unique(
                [_lang_value(movie, "wikidata_description", trans_attr=attr), movie.description if lang_code not in {"uk", "kk"} else ""]
            )
            related_names = _join_unique(
                [
                    type_of_work_name,
                    *(_lang_value(item, "name", trans_attr=attr) for item in getattr(movie, f"_search_genres_{lang_code}")),
                    *(_lang_value(item, "name", trans_attr=attr) for item in getattr(movie, f"_search_actors_{lang_code}")),
                    *(_lang_value(item, "name", trans_attr=attr) for item in getattr(movie, f"_search_countries_{lang_code}")),
                    *(_lang_value(item, "name", trans_attr=attr) for item in getattr(movie, f"_search_studios_{lang_code}")),
                    *(_lang_value(item, "name", trans_attr=attr) for item in getattr(movie, f"_search_directors_{lang_code}")),
                    *(_lang_value(item, "name", trans_attr=attr)for item in getattr(movie, f"_search_screenwriters_{lang_code}")),
                    *(_lang_value(item, "name", trans_attr=attr) for item in getattr(movie, f"_search_producers_{lang_code}")),
                    *(_lang_value(item, "name", trans_attr=attr) for item in getattr(movie, f"_search_composers_{lang_code}")),
                    *(tag.name for tag in movie.tags.all() if lang_code not in {"uk", "kk"}),
                ]
            )
            identifiers = _join_unique(
                [movie.year, movie.imdb_id, movie.wikidata_id] if lang_code not in {"uk", "kk"} else []
            )

            language_vector = _build_search_vector(
                text_a=names,
                text_b=descriptions,
                text_c=related_names,
                text_d=identifiers,
                config_lang=language
            )

            if combined_vector is None:
                combined_vector = language_vector
            else:
                combined_vector += language_vector

        documents.append(
            GlobalSearchIndex(
                content_type=content_type,
                object_id=movie.pk,
                search_vector=combined_vector,
            )
        )
        prepared_count += 1

        if len(documents) >= BATCH_SIZE:
            GlobalSearchIndex.objects.bulk_create(
                documents,
                batch_size=BATCH_SIZE,
                ignore_conflicts=True,
            )
            documents.clear()

    if documents:
        GlobalSearchIndex.objects.bulk_create(
            documents,
            batch_size=BATCH_SIZE,
            ignore_conflicts=True,
        )

    logger.info(
        "Prepared %s new movie search documents for insertion.",
        prepared_count,
    )


def refresh_movie_documents(movie_ids):
    """Atomically refresh only a bounded batch; preserve the rest of the index."""
    movie_ids = list(movie_ids)
    if not movie_ids:
        return
    with transaction.atomic():
        content_type = ContentType.objects.get_for_model(Movie)
        GlobalSearchIndex.objects.filter(content_type=content_type, object_id__in=movie_ids).delete()
        index_new_movies(movie_ids=movie_ids)


def index_new_reviews():
    content_type = ContentType.objects.get_for_model(Review)
    indexed_object_ids = GlobalSearchIndex.objects.filter(
        content_type=content_type
    ).values_list("object_id", flat=True)

    reviews = (
        Review.objects.filter(user__is_deleted=False, user__is_active=True)
        .exclude(pk__in=indexed_object_ids)
        .exclude(text__isnull=True)
        .exclude(text__regex=r"^\s*$")
        .select_related("user", "movie", "movie__type_of_work")
        .only(
            "pk",
            "text",
            "user_id",
            "user__username",
            "movie_id",
            "movie__name",
            "movie__type_of_work_id",
        )
        .prefetch_related(
            _translation_prefetch("movie__translations", Movie, ENGLISH_TRANSLATIONS_ATTR, lang_code="en"),
            _translation_prefetch(
                "movie__type_of_work__translations", TypeOfWork, ENGLISH_TRANSLATIONS_ATTR, lang_code="en"
            ),
            Prefetch(
                "movie__genres",
                queryset=_lang_named_queryset(Genre, ENGLISH_TRANSLATIONS_ATTR, lang_code="en"),
                to_attr="_search_genres",
            ),
        )
    )

    documents = []
    prepared_count = 0

    for review in reviews.iterator(chunk_size=BATCH_SIZE):
        type_of_work_name = ""
        if review.movie.type_of_work is not None:
            type_of_work_name = _lang_value(
                review.movie.type_of_work,
                "name", trans_attr=ENGLISH_TRANSLATIONS_ATTR
            )

        movie_names = _join_unique(
            [_lang_value(review.movie, "wikidata_name", trans_attr=ENGLISH_TRANSLATIONS_ATTR), review.movie.name]
        )
        review_context = _join_unique(
            [
                review.user.username,
                type_of_work_name,
                *(
                    _lang_value(genre, "name", trans_attr=ENGLISH_TRANSLATIONS_ATTR)
                    for genre in review.movie._search_genres
                ),
            ]
        )

        documents.append(
            GlobalSearchIndex(
                content_type=content_type,
                object_id=review.pk,
                search_vector=_build_search_vector(
                    text_a=_clean_text(review.text),
                    text_b=movie_names,
                    text_c=review_context,
                ),
            )
        )
        prepared_count += 1

        if len(documents) >= BATCH_SIZE:
            GlobalSearchIndex.objects.bulk_create(
                documents,
                batch_size=BATCH_SIZE,
                ignore_conflicts=True,
            )
            documents.clear()

    if documents:
        GlobalSearchIndex.objects.bulk_create(
            documents,
            batch_size=BATCH_SIZE,
            ignore_conflicts=True,
        )

    logger.info(
        "Prepared %s new review search documents for insertion.",
        prepared_count,
    )


def index_new_users():
    content_type = ContentType.objects.get_for_model(User)
    indexed_object_ids = GlobalSearchIndex.objects.filter(
        content_type=content_type
    ).values_list("object_id", flat=True)

    users = (
        User.objects.filter(is_deleted=False, is_active=True)
        .exclude(pk__in=indexed_object_ids)
        .only("pk", "username")
    )

    documents = []
    prepared_count = 0

    for user in users.iterator(chunk_size=BATCH_SIZE):
        documents.append(
            GlobalSearchIndex(
                content_type=content_type,
                object_id=user.pk,
                search_vector=_build_search_vector(
                    text_a=_clean_text(user.username)
                ),
            )
        )
        prepared_count += 1

        if len(documents) >= BATCH_SIZE:
            GlobalSearchIndex.objects.bulk_create(
                documents,
                batch_size=BATCH_SIZE,
                ignore_conflicts=True,
            )
            documents.clear()

    if documents:
        GlobalSearchIndex.objects.bulk_create(
            documents,
            batch_size=BATCH_SIZE,
            ignore_conflicts=True,
        )

    logger.info(
        "Prepared %s new user search documents for insertion.",
        prepared_count,
    )


def index_new_persons():
    content_type = ContentType.objects.get_for_model(Person)
    indexed_object_ids = GlobalSearchIndex.objects.filter(
        content_type=content_type
    ).values_list("object_id", flat=True)

    persons = (
        Person.objects.exclude(pk__in=indexed_object_ids)
        .only("pk", "wikidata_id")
        .prefetch_related(
            _translation_prefetch("translations", Person, ENGLISH_TRANSLATIONS_ATTR, lang_code="en")
        )
    )

    documents = []
    prepared_count = 0

    for person in persons.iterator(chunk_size=BATCH_SIZE):
        documents.append(
            GlobalSearchIndex(
                content_type=content_type,
                object_id=person.pk,
                search_vector=_build_search_vector(
                    text_a=_lang_value(person, "name", trans_attr=ENGLISH_TRANSLATIONS_ATTR),
                    text_d=_clean_text(person.wikidata_id),
                ),
            )
        )
        prepared_count += 1

        if len(documents) >= BATCH_SIZE:
            GlobalSearchIndex.objects.bulk_create(
                documents,
                batch_size=BATCH_SIZE,
                ignore_conflicts=True,
            )
            documents.clear()

    if documents:
        GlobalSearchIndex.objects.bulk_create(
            documents,
            batch_size=BATCH_SIZE,
            ignore_conflicts=True,
        )

    logger.info(
        "Prepared %s new person search documents for insertion.",
        prepared_count,
    )


def index_new_studios():
    content_type = ContentType.objects.get_for_model(Studio)
    indexed_object_ids = GlobalSearchIndex.objects.filter(
        content_type=content_type
    ).values_list("object_id", flat=True)

    studios = (
        Studio.objects.exclude(pk__in=indexed_object_ids)
        .only("pk", "wikidata_id")
        .prefetch_related(
            _translation_prefetch("translations", Studio, ENGLISH_TRANSLATIONS_ATTR, lang_code="en")
        )
    )

    documents = []
    prepared_count = 0

    for studio in studios.iterator(chunk_size=BATCH_SIZE):
        documents.append(
            GlobalSearchIndex(
                content_type=content_type,
                object_id=studio.pk,
                search_vector=_build_search_vector(
                    text_a=_lang_value(studio, "name", trans_attr=ENGLISH_TRANSLATIONS_ATTR),
                    text_d=_clean_text(studio.wikidata_id),
                ),
            )
        )
        prepared_count += 1

        if len(documents) >= BATCH_SIZE:
            GlobalSearchIndex.objects.bulk_create(
                documents,
                batch_size=BATCH_SIZE,
                ignore_conflicts=True,
            )
            documents.clear()

    if documents:
        GlobalSearchIndex.objects.bulk_create(
            documents,
            batch_size=BATCH_SIZE,
            ignore_conflicts=True,
        )

    logger.info(
        "Prepared %s new studio search documents for insertion.",
        prepared_count,
    )
