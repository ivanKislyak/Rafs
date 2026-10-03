from django.contrib.contenttypes.models import ContentType
from movies.models import GlobalSearchIndex, Movie, Review
from accounts.models import User

def update_all_exist_indexes():
    gin_qty_on_start = GlobalSearchIndex.objects.count()
    
    print(f'Quantity of GIN objects: {gin_qty_on_start}')
 
    movie_data = []

    all_movies = Movie.objects.all().prefetch_related(
        'translations', 'type_of_work__translations',
        'genres__translations', 'actors__translations',
        'countries__translations', 'studio__translations',
        )

    def flatten_complex_list(data: list, sep=' '):
        def _flatten(item):
            if isinstance(item, (list, tuple)):
                for sub_item in item:
                    yield from _flatten(sub_item)
            elif item is not None:
                yield str(item)

        return sep.join(_flatten(data))

    for movie in all_movies.iterator(chunk_size=1000):
        movie_data.append(
            GlobalSearchIndex(content_type=ContentType.objects.get_for_model(Movie),
                              object_id=movie.pk,
                              search_text=flatten_complex_list(
            [
                [(main_movie_data.wikidata_name, main_movie_data.wikidata_description) for main_movie_data in movie.translations.all()],
                [t.name for t in movie.type_of_work.translations.all()] if movie.type_of_work else [], [t.name for genre in movie.genres.all() for t in genre.translations.all()],
                [t.name for actor in movie.actors.all() for t in actor.translations.all()],
                [t.name for country in movie.countries.all() for t in country.translations.all()],
                [t.name for a_studio in movie.studio.all() for t in a_studio.translations.all()],
                movie.name, movie.description
            ]
        ))
    )
        
    GlobalSearchIndex.objects.bulk_create(
        movie_data
    )