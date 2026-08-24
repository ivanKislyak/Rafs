from django.db import transaction
from movies.models import Movie
from movies.movie_models import TypeOfWork, Genre, Country, Studio, Person
from parler.models import TranslatableModel

LANGUAGES = ["ru", "en", "uk", "kk", "es"]
FIELD_MODEL_MAP = {
    "genres": Genre,
    "countries": Country,
    "studio": Studio,
    "actors": Person,
    "director": Person,
    "producer": Person,
    "screenwriter": Person,
    "composer": Person,
}


def set_lang_for_entity(trans_dict: dict, obj):
    for lang, values in trans_dict.items():
        obj.set_current_language(lang)
        for field_name, field_value in values.items():
            setattr(obj, field_name, field_value)
    obj.save()
    return obj


def return_separated_sets_by_value(info_dict: dict, field: str, related_object: dict) -> list:
    field_qids = info_dict.get(field, set())
    return [related_object[qid] for qid in field_qids if qid in related_object]


def get_or_create_by_qids(model_cls: type[TranslatableModel], qids: set[str]) -> dict:
    existing_entities = model_cls.objects.in_bulk(qids, field_name="wikidata_id")
    missing_qids = qids - existing_entities.keys()
    model_cls.objects.bulk_create(
        [model_cls(wikidata_id=q) for q in missing_qids],
        ignore_conflicts=True,
    )
    return model_cls.objects.in_bulk(qids, field_name="wikidata_id")


def resolve_fallback_name(dict_data: dict, qid: str) -> str:
    names = dict_data.get("wikidata_name", {})
    return names.get("en") or names.get("ru") or next(iter(names.values()), qid)


@transaction.atomic
def import_parsed_data_to_db(qid: str, dict_data: dict):
    type_of_work_obj = None
    if type_of_work_qid := dict_data.get("type_of_work"):
        resolved = get_or_create_by_qids(TypeOfWork, {type_of_work_qid})
        type_of_work_obj = resolved.get(type_of_work_qid)

    source_defaults = {
        "imdb_id": dict_data.get("imdb_id"),
        "year": dict_data.get("year"),
        "type_of_work": type_of_work_obj,
    }

    obj, created = Movie.objects.update_or_create(
        wikidata_id=qid,
        defaults=source_defaults,
        create_defaults={
            **source_defaults,
            "name": resolve_fallback_name(dict_data, qid),
        },
    )

    total_translation = {}
    for lang in LANGUAGES:
        name_value = dict_data.get("wikidata_name", {}).get(lang)
        description_value = dict_data.get("wikidata_description", {}).get(lang)

        if name_value:
            total_translation.setdefault(lang, {})["wikidata_name"] = name_value
        if description_value:
            total_translation.setdefault(lang, {})["wikidata_description"] = description_value

    if total_translation:
        set_lang_for_entity(total_translation, obj)

    qids_by_model = {}
    for field, model in FIELD_MODEL_MAP.items():
        if field in dict_data:
            qids_by_model.setdefault(model, set()).update(dict_data[field])

    resolved_by_model = {
        model: get_or_create_by_qids(model, qids)
        for model, qids in qids_by_model.items()
    }

    for field, model in FIELD_MODEL_MAP.items():
        objects = return_separated_sets_by_value(
            info_dict=dict_data,
            field=field,
            related_object=resolved_by_model.get(model, {}),
        )
        getattr(obj, field).set(objects)

    return obj