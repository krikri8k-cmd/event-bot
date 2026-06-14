# Develop → Production: merge ingest и апгрейдов

Документ для безопасного переноса проверенного функционала с **@MyConductorBot** (develop) на **@MyGuide** (production).

**Статус develop (2026-06-14):** ingest E2E пройден (события 4027/4028), geo entity-links, i18n поиска, аналитика кликов, ExportMessageLink fix.

---

## 1. Окружения (не путать)

| | Develop | Production |
|---|---|---|
| Бот | @MyConductorBot | @MyGuide |
| Railway env | `develop` | `production` |
| Git-ветка | `develop` | `main` |
| Postgres | отдельная БД develop | отдельная БД production |
| Ingest worker | `telegram-ingest` (develop) | **создать/настроить** на production |

**Правило:** production трогаем только по явному «да». Develop остаётся для тестов.

---

## 2. Что уезжает в production (пакет изменений)

### Telegram Ingest (основное)
- Worker `workers/telegram_ingest.py` (Telethon userbot)
- Pipeline: LLM → geo (entity links + Maps) → `events` → модерация → approve
- Таблицы `telegram_sources`, `telegram_ingest_log` (миграция 050)
- Admin-команды ingest, карточки модерации в Nearme
- Отклонение постов без контакта/источника

### Поиск и UI (World)
- i18n пустых состояний и подсказок радиуса (EN/RU)
- Сброс `date_filter` на «сегодня» при новой геолокации
- Fix: не перезаписывать координаты из БД в `venue_enrich`
- Карточки событий, категории BaliForum, ссылки на посты Telegram

### Инфраструктура
- `ExportMessageLinkRequest` из `telethon.tl.functions.channels`
- `user_participation` для аналитики кликов (миграция 020)
- `scripts/debug_geo_resolve.py`, `apply_migration.py` (+ `DATABASE_PUBLIC_URL`)

### Явно НЕ включать
- `AI_GENERATE_SYNTHETIC=0` — оставить выключенным
- Не копировать тестовые `telegram_sources` из develop в production без ревью

---

## 3. Состояние веток (перед merge)

```
develop:  +23 коммита поверх общего предка (ingest, i18n, geo…)
main:     +36 коммита (категории, карточки событий, партнёры…)
```

**Важно:** ветки **разошлись**. Прямой push develop в main без merge **нельзя**.

**Рекомендуемая стратегия (без отката функционала main):**

```text
1. git checkout develop
2. git pull origin develop
3. git merge origin/main          # влить main В develop
4. Разрешить конфликты (см. §4)
5. pytest + smoke на develop
6. PR develop → main (или merge после CI green)
7. Деплой production по §6
```

Так мы **не теряем** доработки main (категории, карточки) и **добавляем** ingest.

---

## 4. Ожидаемые конфликты при merge

Файлы с пересечением изменений (проверено `git merge-tree`):

| Файл | Почему |
|------|--------|
| `bot_enhanced_v3.py` | ingest + i18n vs карточки/категории main |
| `utils/unified_events_service.py` | `categories`, `raw_category`, `time_mode` в INSERT |
| `sources/baliforum.py` | теги категорий |
| `tests/test_*` | тесты карточек и ingest |

**Правило разрешения:** сохранить **оба** набора фич — поля `categories`/`time_mode` из main **и** ingest-хендлеры из develop.

После merge вручную проверить:
- `save_parser_event` / upsert в `unified_events_service.py` — все колонки в INSERT
- `prepare_events` / `render_event_html` — EN + категории + ingest source URL

---

## 5. Миграции БД (production Postgres)

Применять **только** на production, **по порядку**, после бэкапа.

Проверить, что уже есть (`\dt` / Railway Data):

| Миграция | Назначение | Обязательно для ingest |
|----------|------------|------------------------|
| `050_create_telegram_ingest_tables.sql` | `telegram_sources`, `telegram_ingest_log` | **Да** |
| `051_add_events_time_mode.sql` | колонка `time_mode` в `events` | Да (если нет на prod) |
| `052_add_event_categories.sql` | `categories`, `raw_category` | Да (если нет на prod) |
| `020_recreate_user_participation_for_analytics.sql` | аналитика кликов | Рекомендуется |
| `014_create_events_archive_tables.sql` | убрать warning при старте | Опционально |

**Команда (с локальной машины, production public URL):**

```bash
railway run -e production -s Postgres -- \
  python scripts/apply_migration.py migrations/050_create_telegram_ingest_tables.sql

# повторить для 051, 052, 020 — только если таблицы/колонки ещё нет
```

**Проверка ingest-таблиц:**

```sql
SELECT COUNT(*) FROM telegram_sources;
\d telegram_ingest_log
```

**Не применять** develop-специфичные данные (тестовые источники chat_id -5179811176) — только схема.

---

## 6. Railway production: сервисы и env

### Сервис `event-bot` (уже есть)
- Деплой из ветки `main` после merge
- `TELEGRAM_TOKEN` = токен **@MyGuide**
- `BOT_USERNAME=MyGuide` (или актуальный)
- `API_BASE_URL` = URL production event-bot (для `/internal/telegram-ingest/notify`)
- `INTERNAL_INGEST_SECRET` = **новый** секрет (совпадает с worker)
- `MODERATION_CHAT_ID` = чат модерации **production** (не develop Nearme)
- `OPENAI_API_KEY`, `GOOGLE_MAPS_API_KEY` — production ключи
- `AI_GENERATE_SYNTHETIC=0`

### Сервис `telegram-ingest` (новый или клон develop)
- **Start command:** `python workers/telegram_ingest.py`
- `TELEGRAM_INGEST_ENABLED=1` (сначала можно `0` для деплоя без слушания)
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_STRING_SESSION` — **отдельная** userbot-сессия (не бот-токен)
- `DATABASE_URL` = **production** Postgres (internal URL на Railway)
- Те же `OPENAI_API_KEY`, `GOOGLE_MAPS_API_KEY`

### Порядок деплоя (критично)

```text
1. Бэкап production Postgres (Railway snapshot)
2. Миграции БД (§5)
3. Merge develop → main, push
4. railway up -e production -s event-bot -d
5. railway up -e production -s telegram-ingest -d
6. TELEGRAM_INGEST_ENABLED=0 → проверить health → =1
7. Добавить 1 тестовый telegram_source (закрытая группа)
8. Smoke (§7)
```

**Не деплоить** production ingest на все группы сразу — начать с одной тестовой, `trust_level=moderated`.

---

## 7. Smoke-тест после production deploy

### A. Бот @MyGuide (без ingest)
- [ ] `/start`, меню EN/RU
- [ ] «События рядом» + геолокация → список (старые события на месте)
- [ ] «Завтра» / смена радиуса
- [ ] Карточки: категории BaliForum, «Details», кликабельная локация
- [ ] Клик «Маршрут» → нет `UndefinedTable` в логах

### B. Ingest (после включения worker)
- [ ] Пост в тестовой группе с гиперссылкой «Кино здесь» + @контакт
- [ ] Лог ingest: `entity_links=N`, `google_maps_entity_link`, **нет** `exportMessageLink failed`
- [ ] Карточка модерации в production Nearme
- [ ] Approve → `status=open`
- [ ] Поиск у места → событие в 5 km

### C. Регрессия main
- [ ] События пользователей / community не пропали
- [ ] BaliForum / KudaGo парсинг (scheduler) без ошибок в логах

---

## 8. Откат (если что-то пошло не так)

| Уровень | Действие |
|---------|----------|
| Ingest только | `TELEGRAM_INGEST_ENABLED=0` на production worker — новые посты не обрабатываются |
| Бот | Redeploy предыдущего deployment event-bot в Railway |
| БД | Миграции additive — откат SQL только из бэкапа snapshot |
| Git | `main` revert merge commit; develop не трогать |

**Не делать:** `git push --force` на main, `DROP TABLE events`, миграции на production без бэкапа.

---

## 9. Автотесты (прогон перед merge)

На ветке `develop` после `merge origin/main`:

```bash
# Ключевые тесты (без полной БД)
python -m pytest tests/test_telegram_ingest_pr2.py \
  tests/test_events_search_i18n.py \
  tests/test_google_maps_link_coords.py -q

# Полный CI (как GitHub Actions)
DATABASE_URL=postgresql://test:test@localhost:5432/test \
  GOOGLE_MAPS_API_KEY=test OPENAI_API_KEY=test TELEGRAM_TOKEN=test \
  pytest -q
```

**Результат на develop (2026-06-14):** 27/27 passed (ingest + i18n + maps).

Тесты, импортирующие `bot_enhanced_v3.py`, требуют валидный `DATABASE_URL` в окружении (как в CI).

---

## 10. Чеклист «готово к production»

- [ ] `git merge origin/main` в develop, конфликты решены
- [ ] CI green на develop
- [ ] Бэкап production DB
- [ ] Миграции 050/051/052/020 на production
- [ ] Env vars production (§6) — секреты не из develop
- [ ] `telegram-ingest` сервис создан на production
- [ ] `telegram_sources`: только нужные prod-группы (не тестовый chat develop)
- [ ] Smoke §7 пройден
- [ ] @MyConductorBot (develop) **оставить** для регрессии

---

## 11. Что уже проверено на develop

| Компонент | Результат |
|-----------|-----------|
| Ingest LLM + geo entity links | ✅ 4027 IMAX, 0.04 km от кинотеатра |
| Модерация → approve → поиск | ✅ пользователь подтвердил |
| i18n поиска EN | ✅ |
| `user_participation` / click_route | ✅ |
| `ExportMessageLink` fix | ✅ код задеплоен; подтверждается на следующем посте |
| `events_community_archive` warning | ⚠️ нет таблицы на develop — **не блокер** |

---

## 12. Контакты и скрипты

| Задача | Скрипт / команда |
|--------|------------------|
| Отладка geo | `python scripts/debug_geo_resolve.py "NAME" --ref-url ...` |
| Миграция | `python scripts/apply_migration.py migrations/XXX.sql` |
| Ingest миграция | `python scripts/apply_telegram_ingest_migration.py` |
| Develop deploy | `railway up -e develop -s event-bot -d` |
| Production deploy | `railway up -e production -s event-bot -d` (**только по «да»**) |

---

*Документ обновлять после merge main→develop и после первого production smoke.*
