# RAFS: фильмы по странам производства

`import_country_movies` написан с помощью ИИ (OpenAI Codex). Использует тот же
небольшой слой catalogue_import и runner анимации, Movie, import_one,
HTTP/cache/retry/locks и SQLite. Общие правила, формат состояния, ограничения
discovery, остановка/resume, восстановление поиска и погрешность счётчика
описаны в [README_import_series.md](README_import_series.md).
Новых Django-моделей/полей/миграций нет. Старые state-dir не изменяются.

## Отбор стран

`--countries RU,UA,KZ` — **OR**, а не AND: достаточно хотя бы одной выбранной
страны в **TMDB details.production_countries[].iso_3166_1**. Допускаются совместные
производства. Страны: RU — Россия, UA — Украина, KZ — Казахстан. Регистр и порядок
в аргументе нормализуются; пустой список, SU и неподдерживаемые коды отклоняются.
СССР не превращается в страну-преемника; отдельной опции импорта СССР здесь нет.

Это TMDB movie, с P4947 Wikidata, title/release_date и movie endpoints переводов
и external_ids. Анимация/аниме и самостоятельные короткометражки включены;
Animation/Family, оригинальный язык, русский перевод и 50 голосов не требуются.
По умолчанию min-votes=0. Adult/video и неподходящие P31/P279 исключаются.
Все общие строгие проверки идентичности сохраняются, TMDB-only fallback нет.

Официальная документация discover/movie содержит **with_origin_country**,
но не отдельный with_production_country. Поддержка разделителей AND/OR описана
для ряда конкретных фильтров; для стран такого обещания не даётся.
**origin_country не используется как доказательство production_countries**.
Параметры region, language и with_original_language тоже не решают эту задачу.

Поэтому для быстрого старта выполняется отдельный priority-pass
with_origin_country=RU, затем UA/KZ (только выбранные). ID попадают в общую
очередь с UNIQUE(media_type,tmdb_id); ко-продукция не импортируется трижды.
Сразу после них выполняется общий нефильтрованный movie-pass, затем общий
датированный primary_release_date.gte/lte с разбиением переполнений.
Так можно найти и фильм с production_countries=KZ, но origin_country=US.
Каждый кандидат всё равно проходит окончательную проверку production_countries.

**Цена полноты:** после приоритетных проходов требуется много details запросов
к мировому movie-каталогу, большинство дадут outside_countries. Малый dry-run
не оценивает полный объём и может не создать ни одной карточки. Полный обход
может быть длительным; скорость и число подходящих Movie не обещаются.
Группа без даты за пределами доступных 500 страниц остаётся ограничением,
как и переполненный неделимый день. Общий проход необходим именно потому,
что origin-country фильтр не равнозначен стране производства.

При противоречии известных стран Wikidata P495 (ISO P297) или существующих
ручных связей с TMDB production_countries кандидат пропускается с
country_conflict, конкретными QID/кодами в CSV. Страна без доступного P297 даёт
unverified_country. Неизвестный production_countries — missing_production_countries.
Отсутствие выбранной страны — outside_countries. Русскоязычный фильм США не
становится российским, а украинский на русском языке не исключается.

Частичный P495, не содержащий противоречащих стран, допустим. Страны берутся
из реально подтверждённых Wikidata-связей; отсутствие P495 не превращается
в вымышленный Country. Поэтому отобранная по TMDB карточка может иметь неполный
список стран в RAFS. Ручные связи не удаляются/не заменяются, противоречащие
связи молча не добавляются. Проверка происходит до транзакции import_one;
сеть вне долгой транзакции.

## Команды для Ubuntu

Вначале дождитесь завершения текущего animation/series/другого импортёра:
общая блокировка отклоняет параллельного писателя, а не ставит его в очередь.
Далее:

```bash
cd ~/apps/Rafs
source .venv/bin/activate
python manage.py check
```

Небольшой dry-run (только локальный кеш/очередь/отчёт), затем ограниченный apply:

```bash
python -u manage.py import_country_movies --countries RU,UA,KZ --dry-run --max-candidates 20 --state-dir .rafs_import/country-movies-probe
python -u manage.py import_country_movies --countries RU,UA,KZ --max-candidates 20 --state-dir .rafs_import/country-movies-probe
```

Полный обход OR-выборки без искусственной цели 15000:

```bash
python -u manage.py import_country_movies --countries RU,UA,KZ --min-votes 0
```

Или отдельные страны, **последовательно**:

```bash
python -u manage.py import_country_movies --countries RU --min-votes 0
python -u manage.py import_country_movies --countries UA --min-votes 0
python -u manage.py import_country_movies --countries KZ --min-votes 0
```

Папки по умолчанию соответственно:
.rafs_import/country_movies/RU-UA-KZ/, RU/, UA/, KZ/.
Выбирать вместе или раздельно — решение владельца: раздельные кампании повторяют
часть сетевого обхода, зато имеют независимый прогресс. Movie между ними не
дублируются: действуют точные Wikidata/IMDb проверки. Совместные производства
при следующей кампании учитываются как existing/updated, а не новые.

При необходимости практическая цель новых за кампанию:

```bash
python -u manage.py import_country_movies --countries RU,UA,KZ --target-new 20000
```

Непустые поля/переводы/постеры/пользовательские оценки сохраняются; счётчик
SQLite не включает existing/updated/skipped и может немного недосчитать после
аварии между commit PostgreSQL и SQLite. Для resume повторите команду с теми
же странами/фильтрами и state-dir. Target можно повысить. Для другой выборки
используйте другую папку; чужие SQLite не удаляются и не переписываются.

Tmux с логом и сохранённым exit code Python:

```bash
tmux new -s rafs-country-movies
cd ~/apps/Rafs
source .venv/bin/activate
mkdir -p .rafs_import/country_movies/RU-UA-KZ
set -o pipefail
python -u manage.py import_country_movies --countries RU,UA,KZ --min-votes 0 2>&1 | tee -a .rafs_import/country_movies/RU-UA-KZ/run.log
result=${PIPESTATUS[0]}
echo "Importer exit code: $result"
```

Ctrl+B, затем D — отсоединиться; `tmux attach -t rafs-country-movies` — вернуться.
Ctrl+C — остановка с прогрессом; тот же запуск — resume. После reboot tmux-процесс
нужно запустить заново; сохранённое состояние продолжит кампанию.

Контроль из другого терминала:

```bash
tail -f ~/apps/Rafs/.rafs_import/country_movies/RU-UA-KZ/run.log
python -m json.tool ~/apps/Rafs/.rafs_import/country_movies/RU-UA-KZ/summary.json
```

Причины пропусков: summary.campaign_state.skips_by_reason и import_report.csv;
ограничения страниц/дат — discovery_report.csv. Поиск обновляется порциями
только для затронутых Movie, с прежними en/ru/es/de; uk/kk сохраняются в карточки.
Dry-run не меняет Django и индекс. При аварии до индексирования после завершения
кампании доступна ручная `python manage.py rebuild_search_index`.
Массовые загрузки и production-миграции в рамках разработки не выполнялись.

Официальная документация:
[discover/movie](https://developer.themoviedb.org/reference/discover-movie),
[movie details](https://developer.themoviedb.org/reference/movie-details),
[ограничение страниц](https://developer.themoviedb.org/docs/errors).
