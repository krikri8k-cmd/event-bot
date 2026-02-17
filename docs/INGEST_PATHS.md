# Пути загрузки событий (ingest)

## Активный путь в продакшене

- **Запуск:** `start_production.py` → `start_modern_scheduler()` (поток автоматизации).
- **BaliForum / KudaGo / AI:** `modern_scheduler.run_full_ingest()` → `ingest_baliforum()` / `ingest_kudago()` / `ingest_ai_events()` → **UnifiedEventsService.save_parser_event()** с пакетным или одиночным переводом (title_en, description_en, location_name_en).
- **Вывод:** основной парсинг идёт через modern_scheduler с переводом при сохранении.

## Устаревший путь (ICS / Nexudus)

- **Вызов:** эндпоинт `POST /admin/ingest/run` или старый `scheduler.ingest_once()` по расписанию (если где-то ещё запускается).
- **Источники:** таблица `event_sources` (type = `ics` или `html_nexudus`).
- **Раньше:** `scheduler.ingest_once()` → **ingest.upsert.upsert_event()** без перевода.
- **Сейчас:** в `ingest/upsert.py` добавлен вызов **translate_event_to_english()** перед сохранением; в INSERT/UPDATE включены поля **title_en, description_en, location_name_en**. Единый стандарт с переводом соблюдён.

## Доперевод уже сохранённых событий

- Скрипт **scripts/fix_missing_translations.py** выбирает события с `title_en IS NULL`, прогоняет их через OpenAI и обновляет title_en, description_en, location_name_en.
- Запуск: `python -m scripts.fix_missing_translations` (опции: `--batch`, `--limit`, `--dry-run`).
