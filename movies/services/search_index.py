from django.contrib.postgres.search import SearchVector
from parler.models import TranslationDoesNotExist
from django.contrib.contenttypes.models import ContentType
from movies.models import GlobalSearchIndex, Movie, Review
from movies.movie_models import Person, Studio
from accounts.models import User
from django.db.models import Q, Value
import logging

BATCH_SIZE = 1000

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

def join_en_names(subfield):
    return " ".join(
        field.safe_translation_getter(
            "name", language_code="en", default=""
        ) or ""
        for field in subfield
    )

def index_new_movies():
    logging.info(f"Quantity of GIN objects on start: {GlobalSearchIndex.objects.count()}")
    content_type_of_movie = ContentType.objects.get_for_model(Movie)

    already_movies_in_db = GlobalSearchIndex.objects.filter(
        content_type=content_type_of_movie
        ).values("object_id")
    
    
    all_movies = Movie.objects.exclude(id__in=already_movies_in_db).prefetch_related(
        'translations', 'type_of_work__translations',
        'genres__translations', 'actors__translations',
        'countries__translations', 'studio__translations',
        )

    movie_data = []
    
    for movie in all_movies.iterator(chunk_size=BATCH_SIZE):
        name_en = movie.safe_translation_getter(
            "wikidata_name", language_code="en", default=""
        ) or ""

        description_en = movie.safe_translation_getter(
            "wikidata_description", language_code="en", default=""
        ) or ""

        genres_en = join_en_names(movie.genres.all())
        actors_en = join_en_names(movie.actors.all())
        countries_en = join_en_names(movie.countries.all())

        en_vector = (
            SearchVector(Value(name_en), weight="A", config="english")
            + SearchVector(Value(description_en), weight="B", config="english")
            + SearchVector(Value(genres_en), weight="C", config="english")
            + SearchVector(Value(actors_en), weight="C", config="english")
            + SearchVector(Value(countries_en), weight="C", config="english")
        )
            
        movie_data.append(
            GlobalSearchIndex(content_type=content_type_of_movie,
                              object_id=movie.pk,
                              search_vector=en_vector)
        )

        if len(movie_data) >= BATCH_SIZE:
            GlobalSearchIndex.objects.bulk_create(movie_data, ignore_conflicts=True)
            movie_data.clear()

    GlobalSearchIndex.objects.bulk_create(movie_data, ignore_conflicts=True)
    logging.info(f"Quantity of GIN objects after adding Movies: {GlobalSearchIndex.objects.count()}")

def update_all_gin_reviews():
    content_type_of_review = ContentType.objects.get_for_model(Review)
    already_reviews_in_db = GlobalSearchIndex.objects.filter(
        content_type=content_type_of_review
        ).values("object_id")
    
    all_reviews = Review.objects.exclude(Q(id__in=already_reviews_in_db) | Q(text__isnull=True) | Q(text__exact="")
                    ).select_related('user', 'movie', 'movie__type_of_work').prefetch_related(
                    'movie__translations', 
                    'movie__type_of_work__translations',
                    'movie__genres', 
                    'movie__genres__translations')

    review_data = []
    for review in all_reviews:
        review_data.append(
            GlobalSearchIndex(content_type=content_type_of_review,
                              object_id=review.pk,
                              search_text=flatten_complex_list(
            [review.user.username, review.user.first_name, review.user.last_name, review.text, 
                [(main_movie_data.wikidata_name, main_movie_data.wikidata_description) for main_movie_data in review.movie.translations.all()],
                [t.name for t in review.movie.type_of_work.translations.all()] if review.movie.type_of_work else [], 
                [t.name for genre in review.movie.genres.all() for t in genre.translations.all()],
                review.movie.name, review.movie.description
            ]
        ))
    )

    GlobalSearchIndex.objects.bulk_create(
        review_data,
        batch_size=1000
    )

    logging.info(f"Quantity of GIN objects after addind Reviews: {GlobalSearchIndex.objects.count()}")

    # should create functions for these:
    # content_type_of_user = ContentType.objects.get_for_model(User)
    # content_type_of_person = ContentType.objects.get_for_model(Person)
    # content_type_of_studio = ContentType.objects.get_for_model(Studio)