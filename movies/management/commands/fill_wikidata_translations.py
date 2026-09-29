from collections import defaultdict
from itertools import islice

import requests
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError


WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
BATCH_SIZE = 50

# Здесь названия Django-моделей и их локализуемое поле.
MODEL_SPECS = {
    "type_of_work": ("TypeOfWork", "name"),
    "genre": ("Genre", "name"),
    "country": ("Country", "name"),
    "studio": ("Studio", "name"),
    "person": ("Person", "name"),
}


def chunks(iterable, size):
    iterator = iter(iterable)
    while batch := list(islice(iterator, size)):
        yield batch


def format_label(value: str) -> str:
    """
    Wikidata часто отдаёт жанры со строчной буквы:
    'пригодницький фільм' -> 'Пригодницький фільм'.

    Не используй .capitalize(), иначе она испортит остальные буквы:
    'Marvel Studios' -> 'Marvel studios'.
    """
    value = value.strip()
    return value[:1].upper() + value[1:]


class Command(BaseCommand):
    help = (
        "Заполняет пустые переводы Genre, Studio и Person из Wikidata. "
        "Существующие ручные переводы не меняет."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            choices=["all", "type_of_work", "genre", "country", "studio", "person"],
            default="all",
            help="Что заполнять. По умолчанию — всё.",
        )
        parser.add_argument(
            "--languages",
            default="en,ru,uk,kk,es,de",
            help="Языки через запятую. Например: ru,en,uk,de",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только показать изменения, ничего не сохранять.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Ограничить число объектов для проверки.",
        )

    def handle(self, *args, **options):
        languages = [
            language.strip()
            for language in options["languages"].split(",")
            if language.strip()
        ]

        if not languages:
            raise CommandError("Укажи хотя бы один язык: --languages ru,en,uk")

        selected = list(MODEL_SPECS)
        if options["model"] != "all":
            selected = [options["model"]]

        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Rafs/1.0 Wikidata translation importer "
                    "(https://github.com/ivanKislyak/Rafs)"
                )
            }
        )

        total_created = 0
        total_skipped = 0
        total_missing = 0

        for spec_name in selected:
            model_name, translated_field = MODEL_SPECS[spec_name]

            try:
                model = apps.get_model("movies", model_name)
            except LookupError as error:
                raise CommandError(
                    f"Не найдена модель movies.{model_name}. "
                    "Проверь MODEL_SPECS в начале файла."
                ) from error

            queryset = (
                model.objects.exclude(wikidata_id__isnull=True)
                .exclude(wikidata_id="")
                .order_by("id")
            )

            if options["limit"]:
                queryset = queryset[: options["limit"]]

            objects_by_qid = defaultdict(list)

            for obj in queryset:
                qid = str(obj.wikidata_id).strip().upper()

                if not qid.startswith("Q") or not qid[1:].isdigit():
                    self.stdout.write(
                        self.style.WARNING(
                            f"[{spec_name}] пропуск #{obj.pk}: "
                            f"некорректный wikidata_id={obj.wikidata_id!r}"
                        )
                    )
                    continue

                objects_by_qid[qid].append(obj)

            if not objects_by_qid:
                self.stdout.write(
                    self.style.WARNING(f"[{spec_name}] объектов с QID не найдено.")
                )
                continue

            self.stdout.write(
                f"\n[{spec_name}] найдено {sum(map(len, objects_by_qid.values()))} "
                f"объектов, {len(objects_by_qid)} уникальных QID."
            )

            for qid_batch in chunks(objects_by_qid.keys(), BATCH_SIZE):
                try:
                    response = session.get(
                        WIKIDATA_API_URL,
                        params={
                            "action": "wbgetentities",
                            "ids": "|".join(qid_batch),
                            "props": "labels",
                            "languages": "|".join(languages),
                            "format": "json",
                            "formatversion": 2,
                        },
                        timeout=20,
                    )
                    response.raise_for_status()
                    entities = response.json().get("entities", {})
                except (requests.RequestException, ValueError) as error:
                    raise CommandError(
                        f"Ошибка запроса к Wikidata: {error}"
                    ) from error

                for qid, objects in objects_by_qid.items():
                    if qid not in qid_batch:
                        continue

                    entity = entities.get(qid, {})
                    labels = entity.get("labels", {})

                    if not labels:
                        total_missing += len(objects)
                        continue

                    for obj in objects:
                        changed_languages = []

                        for language in languages:
                            raw_label = labels.get(language, {}).get("value", "").strip()

                            # Нет именно украинского/русского/etc. label —
                            # ничего не подставляем из английского, чтобы
                            # случайно не записать неправильный перевод.
                            if not raw_label:
                                continue

                            value = format_label(raw_label)

                            if self.has_value(obj, translated_field, language):
                                total_skipped += 1
                                continue

                            changed_languages.append((language, value))

                        if not changed_languages:
                            continue

                        if options["dry_run"]:
                            changes = ", ".join(
                                f"{language}={value!r}"
                                for language, value in changed_languages
                            )
                            self.stdout.write(
                                f"DRY RUN [{spec_name}] #{obj.pk} ({qid}): {changes}"
                            )
                            continue

                        for language, value in changed_languages:
                            self.save_translation(
                                obj=obj,
                                field_name=translated_field,
                                language=language,
                                value=value,
                            )
                            total_created += 1

                        changes = ", ".join(language for language, _ in changed_languages)
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"[{spec_name}] #{obj.pk} ({qid}): заполнено {changes}"
                            )
                        )

        mode = "Проверка завершена" if options["dry_run"] else "Импорт завершён"
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{mode}. "
                f"Добавлено переводов: {total_created}. "
                f"Пропущено существующих: {total_skipped}. "
                f"Без labels в Wikidata: {total_missing}."
            )
        )

    @staticmethod
    def has_value(obj, field_name, language):
        """
        Поддерживает django-parler и JSONField вида:
        {"en": "...", "ru": "..."}.
        """
        if callable(getattr(obj, "safe_translation_getter", None)):
            value = obj.safe_translation_getter(
                field_name,
                language_code=language,
                default="",
                any_language=False,
            )
            return bool(value and str(value).strip())

        value = getattr(obj, field_name, None)
        if isinstance(value, dict):
            return bool(value.get(language, "").strip())

        raise CommandError(
            f"{obj.__class__.__name__}.{field_name} не является "
            "ни parler-переводом, ни JSONField со словарём переводов."
        )

    @staticmethod
    def save_translation(obj, field_name, language, value):
        if callable(getattr(obj, "set_current_language", None)):
            obj.set_current_language(language)
            setattr(obj, field_name, value)
            obj.save()
            return

        translations = dict(getattr(obj, field_name, {}) or {})
        translations[language] = value
        setattr(obj, field_name, translations)
        obj.save(update_fields=[field_name])