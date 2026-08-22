from movies.models import Movie
from movies.movie_models import TypeOfWork, Genre, Country, Studio, Person
from parler.models import TranslatableModel

from django.db import transaction

LANGUAGES = ["ru", "en", "uk", "kk", "es"]

def set_lang_for_entity(trans_dict: dict, obj):
    for lang, values in trans_dict.items():
        obj.set_current_language(lang)
        for field_name, field_value in values.items():
            setattr(obj, field_name, field_value)
    obj.save()

    return obj

def get_or_create_by_qids(model, qids: set[str]) -> dict:
    pass


@transaction.atomic
def import_parsed_data_to_db(qid: str, dict_data: dict):
    person_keys = ['actors', 'director', 'producer', 'screenwriter', 'composer']
    person_qids = set.union(set(), *[dict_data[k] for k in person_keys if k in dict_data])

    existing_by_qid = Person.objects.in_bulk(
        person_qids,
        field_name="wikidata_id"
    )

    missing_qids = person_qids - existing_by_qid.keys()

    Person.objects.bulk_create(
        [Person(wikidata_id=person_entity) for person_entity in missing_qids],
        ignore_conflicts=True)

    all_by_qid = Person.objects.in_bulk(person_qids, field_name="wikidata_id")

    obj, created = Movie.objects.update_or_create(
        wikidata_id=qid,
        defaults={
            "imdb_id": dict_data["imdb_id"],
            "year": dict_data["year"],
            "type_of_work": dict_data["type_of_work"],
        }
    )

    total_translation = {}
    for lang in LANGUAGES:
        wikidata_name_value = dict_data.get("wikidata_name", {}).get(lang)
        wikidata_description_value = dict_data.get("wikidata_description", {}).get(lang)

        if wikidata_name_value:
            total_translation[lang] = {
                "wikidata_name": wikidata_name_value
            }
        
        if wikidata_description_value:
            total_translation[lang] = {
                "wikidata_description": wikidata_description_value
            }           

    if total_translation:
        set_lang_for_entity(total_translation, obj)


    genres_in_db = Genre.objects.filter(wikidata_id__in=dict_data["genres"])

    obj.actors.set(all_by_qid)
    obj.genres.set(genres_in_db)