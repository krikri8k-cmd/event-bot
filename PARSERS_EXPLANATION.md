# Как работают парсеры BaliForum и KudaGo

## 🏗️ Архитектура парсеров

### 1. **BaliForum** - HTML Scraper
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   baliforum.ru  │───▶│  baliforum.py    │───▶│ events_parser   │
│   (HTML сайт)   │    │  (BeautifulSoup) │    │   (БД)          │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

**Что делает:**
- Скрапит HTML страницы baliforum.ru/events
- Парсит карточки событий с помощью BeautifulSoup
- Извлекает: title, starts_at, place_name, url, lat/lng
- Нормализует русские даты в UTC (Asia/Makassar, UTC+8)
- Сохраняет в `events_parser` с `source='baliforum'`

**Особенности:**
- Rate limiting: 1 запрос/сек
- Валидация: пропускает события без времени
- Геокодирование: извлекает координаты из Google Maps ссылок
- Дедупликация: `UNIQUE (source, external_id)`

### 2. **KudaGo** - API Client
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ kudago.com API  │───▶│ kudago_source.py │───▶│ events_parser   │
│ (REST API)      │    │  (httpx client)  │    │   (БД)          │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

**Что делает:**
- Использует официальный API KudaGo v1.4
- Поддерживает только Москву (msk) и СПб (spb)
- Запрос: `GET /events/?location=msk&actual_since=...&actual_until=...`
- Нормализует временные метки в UTC (Europe/Moscow, UTC+3)
- Сохраняет в `events_parser` с `source='kudago'`

**Особенности:**
- Rate limiting: 3 запроса/сек
- Кэширование: 5 минут in-memory
- Пагинация: до 100 событий на страницу
- Dry-run режим: можно тестировать без сохранения

## 🔄 Жизненный цикл событий

### Этап 1: Инжест (Ingest)
```python
# Запускается по расписанию или вручную
scheduler.py → ingest_once() → sources/*.py → events_parser
```

### Этап 2: Поиск в боте
```python
# Пользователь отправляет геолокацию
bot_enhanced_v3.py → UnifiedEventsService → events (view) → prepare_events_for_feed
```

## 📊 Структура данных

### events_parser (исходные данные)
```sql
CREATE TABLE events_parser (
    id SERIAL PRIMARY KEY,
    source VARCHAR(64),           -- 'baliforum' или 'kudago'
    external_id VARCHAR(64),      -- ID из источника
    title VARCHAR(120),
    description TEXT,
    starts_at TIMESTAMP WITH TIME ZONE,
    lat FLOAT,
    lng FLOAT,
    location_name VARCHAR(255),
    location_url TEXT,
    url TEXT,                     -- ссылка на событие
    city VARCHAR(64),             -- 'bali', 'moscow', 'spb'
    country VARCHAR(2),           -- 'ID', 'RU'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### events (унифицированная таблица)
```sql
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    source VARCHAR(64),           -- 'user', 'baliforum', 'kudago'
    external_id VARCHAR(64),
    title VARCHAR(120),
    description TEXT,
    starts_at TIMESTAMP WITH TIME ZONE,
    lat FLOAT,
    lng FLOAT,
    location_name VARCHAR(255),
    location_url TEXT,
    url TEXT,
    city VARCHAR(64),
    country VARCHAR(2),
    organizer_id BIGINT,          -- для пользовательских событий
    status VARCHAR(16) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## ⚙️ Конфигурация

### Переменные окружения
```bash
# BaliForum
ENABLE_BALIFORUM=1
BALIFORUM_BASE_URL=https://baliforum.ru
BALIFORUM_MAX_EVENTS=100
BALIFORUM_REQUESTS_PER_SEC=1

# KudaGo
KUDAGO_ENABLED=true
KUDAGO_DRY_RUN=false
KUDAGO_RPS=3
KUDAGO_TIMEOUT_S=15
KUDAGO_PAGE_SIZE=100
TODAY_MAX_EVENTS=60
```

## 🕐 Временные зоны

### BaliForum (Бали)
- Часовой пояс: `Asia/Makassar` (UTC+8)
- "Сегодня" = от 00:00 до 23:59 по местному времени
- Конвертация в UTC: `local_time.astimezone(UTC)`

### KudaGo (Россия)
- Часовой пояс: `Europe/Moscow` (UTC+3)
- "Сегодня" = от 00:00 до 23:59 по московскому времени
- Конвертация в UTC: `local_time.astimezone(UTC)`

## 🔍 Поиск событий

### SQL запрос (упрощенный)
```sql
SELECT * FROM events
WHERE city = :city
  AND starts_at >= :start_utc
  AND starts_at < :end_utc
  AND (
    lat IS NULL OR lng IS NULL OR
    6371 * acos(
      cos(radians(:user_lat)) * cos(radians(lat)) *
      cos(radians(lng) - radians(:user_lng)) +
      sin(radians(:user_lat)) * sin(radians(lat))
    ) <= :radius_km
  )
ORDER BY starts_at;
```

## 🚨 Частые проблемы

### BaliForum
- **"Нет времени"**: событие пропускается (skip)
- **HTML изменился**: ломается селектор
- **Неправильная TZ**: событие уходит "вчера/завтра"

### KudaGo
- **Неправильное окно**: `actual_since/until` не совпадает
- **Нет координат**: событие попадает, но не проходит радиус
- **Dry-run**: события не сохраняются

### Общие
- **Дедупликация**: `UNIQUE (source, external_id)`
- **Радиус**: используется `<=` для включения границы
- **Время**: все в UTC, "сегодня" по местному времени

## 🧪 Тестирование

### Проверка инжеста
```python
# Запуск парсера
python -c "from sources.baliforum_source import BaliForumSource; source = BaliForumSource(); events = await source.fetch_events(-8.673445, 115.244452, 10)"

# Проверка в БД
SELECT source, COUNT(*) FROM events_parser GROUP BY source;
```

### Проверка поиска
```python
# Через UnifiedEventsService
from utils.unified_events_service import UnifiedEventsService
service = UnifiedEventsService(engine)
events = service.search_events_today('bali', -8.673445, 115.244452, 10)
```

## 📈 Метрики

### BaliForum
- `parsed=N` - успешно обработано
- `skipped_no_time=M` - пропущено без времени
- `errors=K` - ошибки парсинга

### KudaGo
- `kudago_requests` - количество API запросов
- `events_received` - получено событий
- `events_saved` - сохранено в БД
- `api_errors` - ошибки API

## 🔧 Отладка

### Логи
```bash
# Включить DEBUG для парсеров
export LOG_LEVEL=DEBUG

# Проверить метрики
python -c "from sources.kudago_source import METRICS; print(METRICS)"
```

### SQL запросы
```sql
-- События по источникам
SELECT source, city, COUNT(*) as count, 
       MIN(starts_at) as earliest, 
       MAX(starts_at) as latest
FROM events_parser 
GROUP BY source, city;

-- События на сегодня
SELECT source, title, starts_at, lat, lng
FROM events_parser 
WHERE starts_at >= CURRENT_DATE 
  AND starts_at < CURRENT_DATE + INTERVAL '1 day'
ORDER BY starts_at;
```
