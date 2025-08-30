# 🚀 Чек-лист "Перед запуском"

## 📊 База данных

### ✅ Миграции применены в окружении:
```sql
-- Проверить что колонки созданы
\d+ events

-- Должны быть колонки:
-- source, external_id, url, updated_at

-- Должны быть индексы:
-- idx_events_coords, idx_events_starts_at
-- ux_events_source_ext (уникальный)
```

### ✅ Применить миграцию:
```bash
psql "$DATABASE_URL" -f migrations/add_meetup_columns.sql
```

## 🔧 Конфигурация

### ✅ .env заполнен:
```bash
# Обязательные
DATABASE_URL=postgresql+psycopg2://user:pass@host:port/db
TELEGRAM_TOKEN=your_bot_token

# Для Meetup интеграции
MEETUP_API_KEY=your_meetup_api_key

# Опциональные
GOOGLE_MAPS_API_KEY=your_google_maps_key
OPENAI_API_KEY=your_openai_key
```

## 🧪 Тестирование

### ✅ CI зелёный:
```bash
# Лёгкий CI (без внешних зависимостей)
pytest -m "api or db"

# Полный режим (с Postgres)
FULL_TESTS=1 pytest -m "api or db"

# Pre-commit
pre-commit run --all-files
```

## 🔄 Совместимость клиента

### ✅ Обновить места, где читается старый формат `/events/nearby`:

**Было:**
```python
events = response.json()  # список событий
```

**Стало:**
```python
data = response.json()
events = data["items"]    # список событий
count = data["count"]     # количество
```

### ✅ Проверить все клиенты:
- Telegram бот
- Веб-интерфейс
- Мобильные приложения
- Другие интеграции

## 🛠️ Ручная проверка

### ✅ Запустить скрипт проверки:
```bash
# Linux/Mac
./scripts/quick_test.sh

# Windows PowerShell
.\scripts\quick_test.ps1
```

### ✅ Или вручную:
```bash
# 1. Проверить API работает
curl "http://localhost:8000/health"
# Ожидаем: {"status": "ok"}

# 2. Инжест Meetup (если ключ есть)
curl -X POST "http://localhost:8000/events/sources/meetup/sync?lat=-8.6500&lng=115.2160&radius_km=5"
# Ожидаем: {"inserted": N}

# 3. Поиск в радиусе
curl "http://localhost:8000/events/nearby?lat=-8.6500&lng=115.2160&radius_km=5&limit=10"
# Ожидаем: {"items": [...], "count": N}
```

## 🔍 Валидация

### ✅ Проверить валидацию входных данных:
```bash
# Невалидные координаты
curl "http://localhost:8000/events/nearby?lat=100&lng=0"
# Ожидаем: 400 Bad Request

# Невалидный радиус
curl "http://localhost:8000/events/nearby?lat=0&lng=0&radius_km=50"
# Ожидаем: 400 Bad Request
```

## 📈 Мониторинг

### ✅ Логирование настроено:
- Ошибки инжеста
- Количество вставок/обновлений
- Время ответа API
- Rate limiting события

### ✅ Алерты настроены:
- Падение внешних API
- Высокая латентность
- Ошибки базы данных

## 🚀 Готово к запуску!

### ✅ Все пункты выполнены:
- [ ] Миграции применены
- [ ] Конфигурация заполнена
- [ ] CI зелёный
- [ ] Клиенты обновлены
- [ ] Ручная проверка пройдена
- [ ] Валидация работает
- [ ] Мониторинг настроен

### 🎉 Можно запускать в продакшен!

---

## 🔧 Рекомендации "на потом"

### 1. Перейти на DO UPDATE (уже сделано)
- Данные обновляются при повторном инжесте
- Сохраняется идемпотентность

### 2. PostGIS/earthdistance для быстрых радиусных запросов
```sql
-- Установить расширение
CREATE EXTENSION IF NOT EXISTS postgis;

-- Создать GiST индекс
CREATE INDEX idx_events_geom ON events USING GIST (ST_SetSRID(ST_MakePoint(lng, lat), 4326));
```

### 3. Планировщик инжеста
```python
# APScheduler для автоматического синка
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
scheduler.add_job(sync_meetup_job, 'interval', minutes=30)
scheduler.start()
```

### 4. Кэширование
- Redis для кэша результатов поиска
- TTL 5-10 минут для свежести данных

### 5. Метрики
- Prometheus + Grafana
- Мониторинг производительности
- Алерты на SLA нарушения
