# 📋 ТЗ для Cursor: Проверка качества проекта после чистки

## 🎯 Цель

Убедиться, что проект работает стабильно после ревизии:
- весь код приведён к единому стилю,
- события парсятся и сохраняются корректно,
- ссылки кликабельные,
- поиск по радиусу и моменты работают как задумано.

---

## 🔧 Задачи и порядок выполнения

### 1. Проверка окружения

1. **Прогон линтеров и автоформатирования:**
   ```bash
   ruff check . --fix
   black . --check
   ```

2. **Проверка переменных окружения** (все ли подхватываются из `app.local.env`):
   ```python
   import os
   from config import load_settings
   
   settings = load_settings()
   required_keys = [
       "TELEGRAM_TOKEN", "DATABASE_URL", "DEFAULT_RADIUS_KM",
       "MOMENTS_ENABLE", "MOMENT_TTL_OPTIONS", "MOMENT_DAILY_LIMIT",
       "AI_PARSE_ENABLE", "ENABLE_MEETUP_API", "ENABLE_ICS_FEEDS",
       "GEOCODE_ENABLE", "GOOGLE_MAPS_API_KEY"
   ]
   
   missing = [k for k in required_keys if not getattr(settings, k.lower(), None)]
   print("MISSING:", missing or "OK")
   ```

👉 **Ожидание:** все ключи найдены, линтеры без ошибок.

---

### 2. Юнит-тесты

1. **Убедиться, что есть тесты и они зелёные:**
   ```bash
   python -m pytest tests/ -v --tb=short
   ```

2. **Ключевые тесты должны покрывать:**
   - `haversine_km` — правильный расчёт расстояний
   - `sanitize_url` — фильтрация мусорных ссылок (`example.com`, пустые Google Calendar)
   - `prepare_events_for_feed` — убирает дубли и пустые события
   - `render_event_html` — кликабельные ссылки «Источник» и «Маршрут»

👉 **Ожидание:** все тесты проходят.

---

### 3. Dry-run интеграции

1. **Создать `tools/dry_run.py`**, который имитирует запрос пользователя:
   ```bash
   python tools/dry_run.py --lat -8.5069 --lon 115.2625 --radius 10 --when today --verbose
   ```

2. **Логи должны показать:**
   - количество загруженных событий по источникам (`ics=`, `meetup=`, `ai=`, `moments=`)
   - количество отфильтрованных/удалённых
   - итоговый список событий с названием, временем, ссылкой

👉 **Ожидание:** минимум 2–3 валидных события с кликабельными ссылками.

---

### 4. Проверка базы данных

1. **Запросить свежие события:**
   ```sql
   SELECT source, COUNT(*) FROM events 
   WHERE created_at_utc > NOW() - INTERVAL '1 day'
   GROUP BY source;
   ```

2. **Проверить дубли:**
   ```sql
   SELECT title, starts_at::date, location_name, COUNT(*) 
   FROM events 
   GROUP BY 1,2,3 
   HAVING COUNT(*) > 1;
   ```

3. **Проверить моменты:**
   ```sql
   SELECT 
     COUNT(*) as total_moments,
     COUNT(*) FILTER (WHERE is_active = true AND expires_at > NOW()) as active_moments,
     COUNT(*) FILTER (WHERE is_active = true AND expires_at <= NOW()) as expired_moments
   FROM moments;
   ```

👉 **Ожидание:** дубликатов нет, события разных типов отображаются.

---

### 5. Смоук-тест Telegram

1. **Проверить режим:**
   - если `webhook` → `/health` возвращает `200 OK`, `getWebhookInfo` показывает верный URL
   - если `polling` → бот запускается без ошибок

2. **Отправить геолокацию:**
   - проверить хедер со счётчиком (`source=?, user=?, moments=?`)
   - карточки содержат **название, время, место, Источник (клик), Маршрут (клик)**
   - пагинация ◀️▶️ работает
   - расширение радиуса показывает новые события

3. **Проверить моменты:**
   - лимит 2 в день
   - TTL только 30, 60 или 120 минут
   - отображается «Автор @username», а не «Источник»

---

### 6. Проверка ссылок и маршрутов

- Все «Источник» должны вести на реальные сайты или страницы событий
- «Маршрут» должен вести на Google Maps с названием места или адресом
- В логах должно быть:
  - `sanitize_url(): passed` для валидных ссылок
  - `blocked by URL_BLOCKLIST` для мусорных

---

### 7. Производительность

- Один полный цикл парсинга ≤ 30 секунд
- Геокод кэшируется (ttl=86400)
- В логах фиксировать длительность шагов (`fetch_ics`, `parse_html`, `geocode`)

---

### 8. Диагностика

**Проверить команду `/diag_all`**, которая показывает:
- количество событий по категориям за 24 часа
- количество активных моментов
- список источников (ICS/Meetup/AI парсеры)
- текущую конфигурацию системы

---

## ✅ Результат

1. ✅ Код чистый, линтеры зелёные
2. ✅ Все переменные окружения работают через `app.local.env`
3. ✅ Юнит-тесты проходят
4. ✅ Dry-run выводит реальные события
5. ✅ В БД нет дублей
6. ✅ В Telegram: карточки корректные, пагинация и расширение радиуса работают
7. ✅ Моменты ограничены (2/день, TTL 30-120 мин)
8. ✅ `/diag_all` отражает текущее состояние системы

---

## 🚀 Дополнительные проверки

### Проверка импортов после рефакторинга
```python
# Убедиться, что все импорты работают после удаления utils/geo.py
from utils.geo_utils import haversine_km, bbox_around, validate_coordinates
from api.services.events import get_events_nearby
from bot_enhanced_v3 import prepare_events_for_feed, render_event_html
```

### Проверка конфигурации моментов
```python
from config import load_settings
settings = load_settings()
assert settings.moments_enable == True
assert settings.moment_ttl_options == [30, 60, 120]
assert settings.moment_daily_limit == 2
assert settings.moment_max_radius_km == 20
```

### Проверка источников событий
```python
# Проверить, что все источники настроены
assert settings.enable_meetup_api == True
assert settings.enable_ics_feeds == True
assert len(settings.ics_feeds) > 0
```

---

## 📝 Отчёт о проверке

После выполнения всех проверок создать отчёт в формате:

```
# 🔍 Отчёт о проверке качества проекта

## ✅ Пройденные проверки
- [ ] Линтеры и форматирование
- [ ] Переменные окружения
- [ ] Юнит-тесты
- [ ] Dry-run интеграции
- [ ] База данных
- [ ] Telegram бот
- [ ] Ссылки и маршруты
- [ ] Производительность
- [ ] Диагностика

## 📊 Статистика
- Событий в БД: X
- Активных моментов: Y
- Источников: Z
- Время парсинга: N сек

## 🚨 Найденные проблемы
(если есть)

## 🎯 Рекомендации
(если есть)
```

---

**Готово к выполнению!** 🚀
