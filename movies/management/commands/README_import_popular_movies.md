# RAFS: Popular Movie Import

The script was written with the help of AI (OpenAI Codex). It is prepared for the RAFS models on GitHub as of October 14, 2026: Django 5.2.16, django-parler, Movie/Genre/Country/Studio/Person/TypeOfWork.

## What you get

- A list of **up to 10,000 unique candidates** from TMDB Discover, sorted by popularity.desc.
- By default: not adult/video, at least 50 votes, release date no later than the start of the import, animation (TMDB genre 16) excluded. TV series from the TV API are not imported.
- You can choose `--sort vote_count.desc` if recognition by vote count matters more.
- New records are created **only when there is an unambiguous link to Wikidata**. So 10,000 candidates does not mean exactly 10,000 new Movie rows. Existing movies, ambiguous matches, and missing Wikidata IDs reduce the number of new records.
- Wikidata: QID, IMDb ID, date if the TMDB date is missing, type, genres, countries, studios, actors/voice cast, directors, writers, producers, and composers.
- TMDB: localized titles, plots, and posters. If a plot is missing, the Wikidata description is used. The available en/ru/uk/kk/es/de languages are filled in; if the sources have no translation, English text is not substituted and passed off as another language.
- Titles, descriptions, translations, local covers, and RAFS ratings that were already entered are preserved. Relations are added; existing ones are not cleared. `last_synced_at` is updated.
- Covers are w500-size URLs in the existing cover_url field. The RAFS templates already support them. JPEGs are not downloaded into MEDIA_ROOT; internet access will be needed when they are displayed.

## Installation

1. Save `import_popular_movies.py` to:

   `movies/management/commands/import_popular_movies.py`

   This is a new Django management command. Do not replace the existing importers. If needed, create empty `__init__.py` files in management and commands; RAFS already has them.

2. Get the **API Read Access Token** in your TMDB account:
   https://www.themoviedb.org/settings/api

   Add it to your `.env`:

   ```env
   TMDB_READ_TOKEN=your_API_Read_Access_Token_here
   ```

   Alternative: `TMDB_API_KEY` with a v3 API key. If both are set, the Read Token is used. Do not put the key in the Python file itself, on GitHub, or in messages. The command does not save the token in the cache and does not print URLs containing the key. RAFS already reads `.env` via python-dotenv.

3. Add to `.gitignore`:

   ```gitignore
   .rafs_import/
   ```

   The cache can take up hundreds of megabytes. This folder contains the progress state and should not be committed.

4. In the project terminal where manage.py is located, activate your .venv. All dependencies are already listed in RAFS's requirements.txt; the importer needs no new libraries. The project's current migrations must be applied. The script does not change the DB schema.

## First run

Make sure `.env` points to the right development/server DB. Make a regular backup of that DB before a large run.

Check 20 candidates without changing the Django DB:

```powershell
py manage.py import_popular_movies --limit 20 --backfill-limit 20 --dry-run
```

This mode does call the API and writes a separate cache/candidate list, but does not create or update Django models. So after it you can run a real import with the same state-dir and use the cache it produced.

A small real import:

```powershell
py manage.py import_popular_movies --limit 20 --backfill-limit 20
```

Then the full run:

```powershell
py manage.py import_popular_movies --limit 10000
```

On Linux, use `python manage.py ...` instead of `py manage.py ...`.

By default, missing covers of existing movies are searched first, then the list of popular candidates is saved, then movies and related models are filled in. Building the big list takes time; the main import starts after that stage.

## Resuming and reports

Ctrl+C stops the work. Repeat **the same command**: completed candidates are skipped, unfinished ones continue. An unfinished transaction for a single movie is rolled back; movies that were already imported remain in the DB.

In `.rafs_import/`:
- `state.sqlite3` — a separate list/cache/progress store, not the site's main DB;
- `import_report.csv` — TMDB ID, status, Movie pk, and skip reason;
- `cover_report.csv` — results of the cover search for existing movies;
- `run.lock` — an OS lock against parallel runs.

Filters, languages, and the DB are tied to the state-dir. The limit can be raised from 20 to 10000. For a different selection/DB, use a new `--state-dir`; do not delete the current progress. TMDB's sort order changes over time: this is a practical selection of saved candidates, not an exact, unchanging worldwide popularity ranking.

Covers of existing movies only:

```powershell
py manage.py import_popular_movies --covers-only
```

Import without the preliminary search for old covers:

```powershell
py manage.py import_popular_movies --limit 10000 --skip-backfill
```

Retry skipped records after manually fixing IDs, requesting fresh responses:

```powershell
py manage.py import_popular_movies --limit 10000 --retry-skipped --refresh-cache
```

Later, fill in empty fields of previously imported candidates with fresh data:

```powershell
py manage.py import_popular_movies --limit 10000 --reprocess --refresh-cache
```

This command does not overwrite non-empty fields, does not delete relations, and does not update existing GlobalSearchIndex search documents. Search indexing is a separate step.

## Duplicate protection

- The main identity is the Wikidata ID; the IMDb ID is also checked.
- IDs are cross-checked between TMDB, Wikidata, and the existing DB.
- Multiple matches or conflicting IDs lead to a skip, not a merge.
- A title-and-year match is used only to detect a possible old duplicate: such rows are sent for manual review. A movie is never merged by title.
- Related entities are created by unique wikidata_id.
- PostgreSQL gets an advisory lock for the duration of this importer; a separate file lock also protects a standard run with a single state-dir.
- Do not run other bulk importers at the same time, or run this import in a separate SQLite state folder with the same sources. The code does not eliminate duplicates that already exist.

If an old movie has neither a Wikidata ID nor an IMDb ID, a poster cannot be safely matched automatically. Provide the correct ID and repeat the cover search. Duplicates that were already in the DB before the run are not deleted or merged.

## Gentle API usage

- Sequential requests, no threads, proxies, or limit circumvention.
- Minimum intervals: TMDB 0.6 seconds, Wikidata 1 second, SPARQL 5 seconds.
- Wikidata entities are fetched in batches of up to 50 IDs; responses are cached on disk.
- SPARQL is used for small, precise ID matching, not for exporting the whole movie graph. A Wikidata ID already provided by TMDB does not require a SPARQL lookup.
- A real User-Agent and maxlag=5 are used for the Action API.
- 429/5xx/maxlag: limited retries with growing wait times and Retry-After.
- 401/403: immediate stop. After repeated network errors the command also stops, so as not to keep needlessly loading the service.

If you want it slower:

```powershell
py manage.py import_popular_movies --limit 10000 --tmdb-delay 1 --wikidata-delay 2 --sparql-delay 10
```

Nobody can guarantee against blocking or API availability. The script reduces load and respects server responses. For 10,000 candidates, expect several hours; data availability, the network, and server pauses affect the time significantly.

## TMDB attribution

TMDB requires crediting the source in About/Credits, using the approved logo, and including this notice:

> This product uses the TMDB API but is not endorsed or certified by TMDB.

This README does not replace the credit on the site. Non-commercial API use is available when TMDB's terms are met; commercial use is governed separately.

## What was and wasn't verified

- Python syntax.
- The actual current RAFS models with Django 5.2.16 and django-parler 2.4, a separate SQLite DB, and API fixtures: dry-run, re-run, translations, relations, covers, preservation of manual fields and ratings, ID conflict, rollback on error, binding of state to configuration, HTTP 429/Retry-After/403, and a cache without the token.
- One real read-only request to Wikidata to check the response format.
- Not verified: your PostgreSQL, your TMDB token, a live bulk import, and Windows locking. That is why a 20-candidate run is provided first.

## Official sources

- https://developer.themoviedb.org/reference/discover-movie
- https://developer.themoviedb.org/reference/movie-details
- https://developer.themoviedb.org/reference/movie-external-ids
- https://developer.themoviedb.org/reference/movie-translations
- https://developer.themoviedb.org/reference/find-by-id
- https://developer.themoviedb.org/docs/image-basics
- https://developer.themoviedb.org/docs/rate-limiting
- https://developer.themoviedb.org/docs/errors
- https://developer.themoviedb.org/docs/faq
- https://www.mediawiki.org/wiki/API:Etiquette
- https://www.mediawiki.org/wiki/Wikibase/API

Anime, animation, and TV series are intentionally left for a separate, later importer.

---

---

---


# RAFS: импорт популярных фильмов

Скрипт написан с помощью ИИ — OpenAI Codex. Подготовлен под модели RAFS на GitHub
14 октября 2026: Django 5.2.16, django-parler, Movie/Genre/Country/Studio/Person/TypeOfWork.

## Что получится

- Список **до 10 000 уникальных кандидатов** из TMDB Discover, сортировка popularity.desc.
- По умолчанию: не adult/video, минимум 50 голосов, дата выхода не позже начала импорта,
  анимация (жанр TMDB 16) исключена. Сериалы из TV API не импортируются.
- Можно выбрать `--sort vote_count.desc`, если важнее известность по числу голосов.
- Новые записи создаются **только при однозначной связи с Wikidata**. Поэтому 10 000
  кандидатов не означает ровно 10 000 новых строк Movie. Уже существующие фильмы,
  неоднозначные совпадения и отсутствующие Wikidata ID уменьшают число новых записей.
- Wikidata: QID, IMDb ID, дата при отсутствии TMDB-даты, тип, жанры, страны,
  студии, актёры/озвучка, режиссёры, сценаристы, продюсеры и композиторы.
- TMDB: локализованные названия, сюжеты и постеры. При отсутствии сюжета берётся
  описание Wikidata. Заполняются доступные en/ru/uk/kk/es/de; отсутствие перевода у
  источников не заменяется английским текстом под видом другого языка.
- Уже введённые названия, описания, переводы, локальные обложки и RAFS-оценки
  сохраняются. Связи добавляются, существующие не очищаются. `last_synced_at` обновляется.
- Обложки — URL размера w500 в существующем поле cover_url. Их уже поддерживают
  шаблоны RAFS. JPEG не скачиваются в MEDIA_ROOT; интернет потребуется при их показе.

## Установка

1. Сохрани `import_popular_movies.py` в:

   `movies/management/commands/import_popular_movies.py`

   Это новая Django management command. Существующие импортёры не заменяй.
   При необходимости создай пустые `__init__.py` в management и commands; в RAFS они уже есть.

2. Возьми **API Read Access Token** в аккаунте TMDB:
   https://www.themoviedb.org/settings/api

   Добавь в свой `.env`:

   ```env
   TMDB_READ_TOKEN=сюда_твой_API_Read_Access_Token
   ```

   Альтернатива: `TMDB_API_KEY` с v3 API key. Если заданы оба, используется Read Token.
   Не добавляй ключ в сам Python-файл, GitHub или сообщения. Команда не сохраняет
   токен в кэш и не печатает URL с ключом. RAFS уже читает `.env` через python-dotenv.

3. Добавь в `.gitignore`:

   ```gitignore
   .rafs_import/
   ```

   Кэш может занять сотни мегабайт. Эта папка содержит прогресс, её не нужно коммитить.

4. В терминале проекта, где лежит manage.py, активируй свою .venv. Все зависимости
   уже перечислены в requirements.txt RAFS; новых библиотек импортёр не требует.
   Текущие миграции проекта должны быть применены. Скрипт не меняет схему БД.

## Первый запуск

Проверь, что .env указывает на нужную разработческую/серверную БД. Перед большим
запуском сделай обычную резервную копию этой БД.

Проверка 20 кандидатов без изменения Django БД:

```powershell
py manage.py import_popular_movies --limit 20 --backfill-limit 20 --dry-run
```

Этот режим действительно обращается к API и записывает отдельный кэш/список
кандидатов, но не создаёт и не обновляет Django-модели. Поэтому после него можно
запустить настоящий импорт с тем же state-dir, пользуясь полученным кэшем.

Небольшой настоящий импорт:

```powershell
py manage.py import_popular_movies --limit 20 --backfill-limit 20
```

Затем полный запуск:

```powershell
py manage.py import_popular_movies --limit 10000
```

На Linux используй `python manage.py ...` вместо `py manage.py ...`.

По умолчанию сначала ищутся недостающие обложки у существующих фильмов, затем
сохраняется список популярных кандидатов, затем заполняются фильмы и связанные модели.
Создание большого списка занимает время; основной импорт начнётся после этого этапа.

## Продолжение и отчёты

Ctrl+C останавливает работу. Повтори **ту же команду**: завершённые кандидаты
пропускаются, незавершённые продолжаются. Незавершённая транзакция одного фильма
откатывается; уже импортированные фильмы остаются в БД.

В `.rafs_import/`:
- `state.sqlite3` — отдельный список/кэш/прогресс, не основная БД сайта;
- `import_report.csv` — TMDB ID, статус, Movie pk и причина пропуска;
- `cover_report.csv` — результаты поиска обложек для существующих фильмов;
- `run.lock` — ОС-блокировка от параллельного запуска.

Фильтры, языки и БД привязаны к state-dir. Лимит можно увеличить с 20 до 10000.
Для другой выборки/БД используй новый `--state-dir`; не удаляй текущий прогресс.
Сортировка TMDB меняется со временем: это практическая выборка сохранённых кандидатов,
а не точный неизменный мировой рейтинг популярности.

Только обложки существующих фильмов:

```powershell
py manage.py import_popular_movies --covers-only
```

Импорт без предварительного поиска старых обложек:

```powershell
py manage.py import_popular_movies --limit 10000 --skip-backfill
```

Повторить пропущенные записи после ручного исправления ID, запросив свежие ответы:

```powershell
py manage.py import_popular_movies --limit 10000 --retry-skipped --refresh-cache
```

Позже дозаполнить пустые поля ранее импортированных кандидатов свежими данными:

```powershell
py manage.py import_popular_movies --limit 10000 --reprocess --refresh-cache
```

Эта команда не перезаписывает непустые поля, не удаляет связи и не обновляет
существующие поисковые документы GlobalSearchIndex. Индексация поиска — отдельный этап.

## Защита от дублей

- Основная идентичность — Wikidata ID; дополнительно проверяется IMDb ID.
- ID сверяются между TMDB, Wikidata и существующей БД.
- Несколько совпадений или противоречивые ID приводят к пропуску, а не слиянию.
- Совпадение названия и года используется только для обнаружения возможного старого
  дубля: такие строки отправляются на ручной разбор. По названию фильм не объединяется.
- Связанные сущности создаются по уникальному wikidata_id.
- PostgreSQL получает advisory lock на время этого импортёра; отдельная файловая
  блокировка также защищает стандартный запуск с одним state-dir.
- Не запускай одновременно другие массовые импортёры или этот импорт в отдельной
  SQLite state-папке с теми же источниками. Код не устраняет уже имеющиеся дубликаты.

Если у старого фильма нет ни Wikidata ID, ни IMDb ID, безопасно подобрать постер
автоматически не получится. Укажи корректный ID и повтори поиск обложек. Дубли,
которые уже были в базе до запуска, не удаляются и не объединяются.

## Бережное использование API

- Последовательные запросы, без потоков, прокси и обхода ограничений.
- Минимальные интервалы: TMDB 0.6 секунды, Wikidata 1 секунда, SPARQL 5 секунд.
- Wikidata entities получаются пачками до 50 ID; ответы кэшируются на диск.
- SPARQL используется для небольших точных ID-сопоставлений, а не для выгрузки
  всего графа фильмов. Уже указанный в TMDB Wikidata ID не требует SPARQL-поиска.
- Используются настоящий User-Agent и maxlag=5 для Action API.
- 429/5xx/maxlag: ограниченные повторы с растущим ожиданием и Retry-After.
- 401/403: немедленная остановка. После повторных сетевых ошибок команда тоже
  останавливается, чтобы не продолжать бесполезно нагружать сервис.

Если хочешь медленнее:

```powershell
py manage.py import_popular_movies --limit 10000 --tmdb-delay 1 --wikidata-delay 2 --sparql-delay 10
```

Никто не может гарантировать отсутствие блокировки или доступность API. Скрипт
снижает нагрузку и соблюдает ответы сервера. Для 10000 кандидатов рассчитывай на
несколько часов; наличие данных, сеть и серверные паузы сильно влияют на время.

## TMDB attribution

TMDB требует указание источника в About/Credits, утверждённый логотип и уведомление:

> This product uses the TMDB API but is not endorsed or certified by TMDB.

Само наличие этого README не заменяет credit на сайте. Некоммерческое API доступно
при выполнении условий TMDB; коммерческое использование регулируется отдельно.

## Проверено и что не проверено

- Python-синтаксис.
- Настоящие актуальные модели RAFS с Django 5.2.16 и django-parler 2.4,
  отдельная SQLite БД и фикстуры API: dry-run, повторный запуск, переводы, связи,
  обложки, сохранение ручных полей и рейтинга, конфликт ID, откат при ошибке,
  привязка state к конфигурации, HTTP 429/Retry-After/403 и кэш без токена.
- Один реальный read-only запрос к Wikidata для проверки формата ответа.
- Не проверены: твоя PostgreSQL, твой TMDB-токен, живой массовый импорт и
  Windows-блокировка. Поэтому сначала предусмотрен запуск на 20 кандидатов.

## Официальные источники

- https://developer.themoviedb.org/reference/discover-movie
- https://developer.themoviedb.org/reference/movie-details
- https://developer.themoviedb.org/reference/movie-external-ids
- https://developer.themoviedb.org/reference/movie-translations
- https://developer.themoviedb.org/reference/find-by-id
- https://developer.themoviedb.org/docs/image-basics
- https://developer.themoviedb.org/docs/rate-limiting
- https://developer.themoviedb.org/docs/errors
- https://developer.themoviedb.org/docs/faq
- https://www.mediawiki.org/wiki/API:Etiquette
- https://www.mediawiki.org/wiki/Wikibase/API

Аниме, анимация и сериалы намеренно оставлены для следующего отдельного импортёра.
