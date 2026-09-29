from movies.models import GlobalSearchIndex, Movie, Review
from accounts.models import User
from .import_wikidata import LANGUAGES
import locale
import gettext

def update_all_exist_indexes():
    gin_qty_on_start = GlobalSearchIndex.objects.count()
    
    print(f'Quantity of GIN objects: {gin_qty_on_start}')
    # movie_translations = Movie.translations.model.objects.select_related('master').all()
    
    movie_data = []

    all_movies = Movie.objects.all().prefetch_related(
        'translations', 'type_of_work__translations',
        'genres__translations', 'actors__translations',
        'countries__translations', 'studio__translations',
        )

    for movie in all_movies.iterator(chunk_size=1000):
        print(movie, movie.year, [(main_movie_data.wikidata_name, main_movie_data.wikidata_description) for main_movie_data in movie.translations.all()],
              [t.name for t in movie.type_of_work.translations.all()] if movie.type_of_work else [], [t.name for genre in movie.genres.all() for t in genre.translations.all()],
              [t.name for actor in movie.actors.all() for t in actor.translations.all()],
              [t.name for country in movie.countries.all() for t in country.translations.all()],
              [t.name for a_studio in movie.studio.all() for t in a_studio.translations.all()],
             )
    
    # for movie_translation in movie_translations:
    #     movie_data.append(
    #         (movie_translation.master_id,
    #         (f"{movie_translation.wikidata_name} "
    #          f"{movie_translation.wikidata_description} "
    #          f"{movie_translation.master.year} "
    #          f"{movie_translation.master.actors.translations.name}")
    #          )
    #          ) 

    # movies_ids = Movie.objects.values('id', 'wikidata_id')


    # existing_movies_in_gin = set(
    # User.objects.filter(email__in=emails_to_check).values_list('email', flat=True)
    # )

    # new_movies = [email for email in emails_to_check if email not in existing_emails]


    GlobalSearchIndex.objects.bulk_create(movie_data)
    
    for lang in LANGUAGES:
        try:
            pass
        except FileNotFoundError:
            pass