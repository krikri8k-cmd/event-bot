# Диагностика системы перевода (title_en)

**Цель:** выяснить, почему в БД остаются события с `title_en IS NULL`.

---

## 1. Аудит путей загрузки (Trace Entry Points)

### Где сохраняются события (Event)

| Путь | Файл | Вызов перевода? | Комментарий |
|------|------|-----------------|-------------|
| **ingest/upsert.py** `upsert_event()` | scheduler.py (ICS, Nexudus), api/ingest (если есть) | ✅ Да | Вызывает `translate_event_to_english()` при `title_en is None`. |
| **utils/unified_events_service.py** `save_parser_event()` | modern_scheduler.py, run_baliforum_ingest.py, parser_integration.py | ✅ Да | Перевод при новой записи или при `title_en` в БД NULL. |
| **ingest.py** `upsert_events()` | **api/app.py** (Meetup, BaliForum sync) | ❌ **Нет** | **Критично:** INSERT вообще не содержит колонок `title_en`, `description_en`, `location_name_en`. События попадают в БД с `title_en = NULL`. |

### Вывод по п.1

**Есть сценарий обхода перевода:** эндпоинты API  
`POST /events/sources/meetup/sync` и `POST /events/sources/baliforum/sync`  
используют `from ingest import upsert_events` (модуль **ingest.py**), который делает сырой INSERT/UPDATE без полей перевода и без вызова `translate_event_to_english()`.  

Если события «ЛИЛА» и «Мафия» загружались через эти API, у них будет `title_en IS NULL`.

**Рекомендация:** перевести API на использование `ingest.upsert.upsert_event()` (из **ingest/upsert.py**) или добавить в `ingest.py` вызов перевода и поля `title_en`/`description_en`/`location_name_en` в INSERT.

---

## 2. Проверка логики «пропуска» (Skip Logic)

### ingest/upsert.py

- Условие перевода: `if title_en is None and (title or description or location_name):`
- **Проблема:** если в `row` уже пришло `title_en = ""` (пустая строка), условие **не срабатывает** — перевод не вызывается, в БД уходит пустая строка.
- В скриптах аудита и бэкфилла уже учитывается и NULL, и пустая строка: `WHERE title_en IS NULL OR title_en = ''`.

**Рекомендация:** считать «нет перевода» и для пустой строки, например:  
`if (title_en is None or (title_en or "").strip() == "") and (title or description or location_name):`

### utils/unified_events_service.py (save_parser_event)

- `existing_has_title_en = bool(existing_title_en and (existing_title_en or "").strip())`
- При `existing_title_en = ''` или `None` получается `False` — перевод **вызывается**. Ложного «уже переведено» нет.
- При переданном снаружи `title_en is not None` (batch) перевод не вызывается — ожидаемо.

**Вывод:** в `save_parser_event` пустая строка не считается «уже переведённым». Проблема только в **ingest/upsert.py** (см. выше).

---

## 3. Анализ обработки ошибок OpenAI

- В `utils/event_translation.py` при любой ошибке функция возвращает словарь с `title_en: None`, `description_en: None`, `location_name_en: None` (не бросает исключение наружу).
- В **ingest/upsert.py** при исключении из перевода: `logger.warning(...)`, в `title_en` ничего не подставляется — остаётся `None`. Русский текст в `title_en` **не записывается**.
- В **unified_events_service.py** при отсутствии `trans.get("title_en")` подставляется `existing_row[3]` или `None` — в БД не пишется пустая строка вместо перевода.

**Вывод:** при падении перевода поле `title_en` остаётся NULL; оригинал в `title_en` не дублируется. Ошибки логируются (warning/error в event_translation и при необходимости в вызывающем коде). Для разбора сбоев смотреть логи Railway (поиск по `event_translation` / `перевод не выполнен`).

---

## 4. Сверка по конкретным примерам (ЛИЛА, Мафия)

Для проверки можно запустить скрипт (см. ниже):

```bash
python scripts/find_events_by_title.py "ЛИЛА" "Мафия"
```

Скрипт выведет по каждому совпадению: `id`, `source`, `external_id`, `title`, `title_en`. По ним можно понять:
- через какой источник зашло событие (source);
- по external_id — из какого парсера/источника;
- если `source` приходит с API (и запись создана через `ingest.upsert_events`), причина отсутствия перевода — обход перевода в API (п.1).

---

## 5. Статус location_name

**Да, `location_name` сейчас переводится через GPT.**

- В `utils/event_translation.py` в промпт добавляется поле `location_name` (если не пустое), в ответе ожидается `location_name_en`.
- Системный промпт просит переводить «название и текст события»; отдельного исключения для названий мест нет.
- Значение записывается в БД в `location_name_en` (ingest/upsert.py, unified_events_service.py).

Если нужно **запретить** перевод названия места через GPT, следует:
- не передавать `location_name` в `translate_event_to_english` / не добавлять его в промпт, и/или
- не записывать `location_name_en` из ответа GPT (оставлять NULL или копировать оригинал).

---

## Краткий чеклист исправлений

1. **API sync (Meetup/BaliForum):** перевести на `ingest.upsert.upsert_event()` или добавить перевод и колонки _en в `ingest.py`.
2. **ingest/upsert.py:** учитывать пустую строку как «нет перевода»: `(title_en is None or (title_en or "").strip() == "")`.
3. **location_name:** при необходимости отключить перевод — убрать из промпта и не писать в `location_name_en` из GPT.
4. Запустить скрипт поиска событий «ЛИЛА»/«Мафия» и по результатам подтвердить источник и причину отсутствия перевода.
