from django.contrib.postgres.search import SearchVector
from parler.models import TranslationDoesNotExist
from django.contrib.contenttypes.models import ContentType
from movies.models import GlobalSearchIndex, Movie, Review
from movies.movie_models import Person, Studio
from accounts.models import User
from django.db.models import Q, Value
import logging

logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)

def flatten_complex_list(data: list, sep=' '):
        result = []
        stack = [data]

        while stack:
            item = stack.pop()

            if isinstance(item, (list, tuple)):
                stack.extend(reversed(item))
            elif item is not None:
                result.append(str(item))

        return sep.join(result)

def update_all_exist_indexes():
    logging.info(f"Quantity of GIN objects on start: {GlobalSearchIndex.objects.count()}")

    content_type_of_movie = ContentType.objects.get_for_model(Movie)
    content_type_of_review = ContentType.objects.get_for_model(Review)
    content_type_of_user = ContentType.objects.get_for_model(User)
    content_type_of_person = ContentType.objects.get_for_model(Person)
    content_type_of_studio = ContentType.objects.get_for_model(Studio)

    already_movies_in_db = GlobalSearchIndex.objects.filter(
        content_type=content_type_of_movie
        ).values("object_id")
    
    
    all_movies = Movie.objects.exclude(id__in=already_movies_in_db).prefetch_related(
        'translations', 'type_of_work__translations',
        'genres__translations', 'actors__translations',
        'countries__translations', 'studio__translations',
        )


    movie_data = []
    for movie in all_movies:
        en_vector = (
            SearchVector(
                Value(
                    wd_name_ru = movie.safe_translation_getter(
                        'wikidata_name', language_code='en')),
                        weight='A', config='english'
            ) +
            SearchVector(
                Value(
                    wd_desc_ru = movie.safe_translation_getter(
                        'wikidata_description', language_code='en')),
                        weight='B', config='english'
            ) +
            SearchVector(
                    
            )
            )
        
        ru_vector = (
             SearchVector(
                Value(
                    wd_name_ru = movie.safe_translation_getter('wikidata_name', language_code='ru')), 
                    weight='A', 
                    config='russian') +
                SearchVector(
                    Value(
                        
                    )
                )
        )

        de_vector = (
             SearchVector(
                Value(
                    wd_name_ru = movie.safe_translation_getter('wikidata_name', language_code='de')), 
                    weight='A', 
                    config='german') +
                SearchVector(
                    Value(
                        
                    )
                )
        )

        es_vector = (
             SearchVector(
                Value(
                    wd_name_ru = movie.safe_translation_getter('wikidata_name', language_code='es')), 
                    weight='A', 
                    config='spanish') +
                SearchVector(
                    Value(
                        
                    )
                )
        )
            
        

        movie_data.append(
            GlobalSearchIndex(content_type=content_type_of_movie,
                              object_id=movie.pk,
                              search_text=flatten_complex_list(
            [
                [(main_movie_data.wikidata_name, main_movie_data.wikidata_description) for main_movie_data in movie.translations.all()],
                [t.name for t in movie.type_of_work.translations.all()] if movie.type_of_work else [], 
                [t.name for genre in movie.genres.all() for t in genre.translations.all()],
                [t.name for actor in movie.actors.all() for t in actor.translations.all()],
                [t.name for country in movie.countries.all() for t in country.translations.all()],
                [t.name for a_studio in movie.studio.all() for t in a_studio.translations.all()],
                movie.name, movie.description
            ]
        ))
    )

    GlobalSearchIndex.objects.bulk_create(
        movie_data,
        batch_size=1000
    )

    logging.info(f"Quantity of GIN objects after addind Movies: {GlobalSearchIndex.objects.count()}")
    
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
