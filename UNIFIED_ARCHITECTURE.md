# 🎯 Единая архитектура событий

## 📋 Обзор

Архитектура событий была упрощена до **3 таблиц** с четким разделением ответственности:

1. **`events_parser`** - события от парсеров (BaliForum, KudaGo, AI)
2. **`events_user`** - события от пользователей
3. **`events`** - **ЕДИНАЯ ТАБЛИЦА** где бот читает ВСЕ события

## 🏗️ Структура

### Таблица `events_parser`
```sql
CREATE TABLE events_parser (
    id SERIAL PRIMARY KEY,
    source VARCHAR(64) NOT NULL,           -- baliforum, kudago, ai
    external_id VARCHAR(255) NOT NULL,     -- ID из источника
    title VARCHAR(255) NOT NULL,
    description TEXT,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ,
    url TEXT,
    location_name VARCHAR(255),
    location_url TEXT,
    lat DECIMAL(10,8),
    lng DECIMAL(11,8),
    country VARCHAR(10),                   -- ID, RU
    city VARCHAR(64),                      -- bali, moscow, spb
    venue_name VARCHAR(255),
    address TEXT,
    community_name VARCHAR(255),
    community_link TEXT,
    created_at_utc TIMESTAMPTZ DEFAULT NOW(),
    updated_at_utc TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source, external_id)
);
```

### Таблица `events_user`
```sql
CREATE TABLE events_user (
    id SERIAL PRIMARY KEY,
    organizer_id BIGINT NOT NULL,
    organizer_username VARCHAR(255),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ,
    url TEXT,
    location_name VARCHAR(255),
    location_url TEXT,
    lat DECIMAL(10,8),
    lng DECIMAL(11,8),
    country VARCHAR(10),                   -- ID, RU
    city VARCHAR(64),                      -- bali, moscow, spb
    max_participants INTEGER,
    current_participants INTEGER DEFAULT 0,
    participants_ids TEXT,                 -- JSON array of user IDs
    status VARCHAR(64) DEFAULT 'open',     -- open, closed, cancelled
    community_name VARCHAR(255),
    community_link TEXT,
    created_at_utc TIMESTAMPTZ DEFAULT NOW(),
    updated_at_utc TIMESTAMPTZ DEFAULT NOW()
);
```

### Таблица `events` (ЕДИНАЯ)
```sql
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    source VARCHAR(64) NOT NULL,           -- user, baliforum, kudago, ai
    external_id VARCHAR(255),              -- ID из источника или events_user.id
    title VARCHAR(255) NOT NULL,
    description TEXT,
    time_local VARCHAR(255),
    event_tz VARCHAR(64),
    time_utc TIMESTAMPTZ,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ,
    url TEXT,
    location_name VARCHAR(255),
    location_url TEXT,
    lat DECIMAL(10,8),
    lng DECIMAL(11,8),
    organizer_id BIGINT,                   -- только для user событий
    organizer_username VARCHAR(255),
    max_participants INTEGER,
    participants_ids TEXT,
    current_participants INTEGER DEFAULT 0,
    status VARCHAR(64) DEFAULT 'open',
    created_at_utc TIMESTAMPTZ DEFAULT NOW(),
    updated_at_utc TIMESTAMPTZ DEFAULT NOW(),
    community_name VARCHAR(255),
    community_link TEXT,
    is_generated_by_ai BOOLEAN DEFAULT FALSE,
    dedupe_key VARCHAR(255),
    country VARCHAR(10),                   -- ID, RU
    city VARCHAR(64)                       -- bali, moscow, spb
);
```

## 🔄 Логика работы

### Запись событий

1. **Парсерные события:**
   ```
   Парсер → events_parser → автоматическая синхронизация → events
   ```

2. **Пользовательские события:**
   ```
   Пользователь → events_user → автоматическая синхронизация → events
   ```

### Чтение событий

**Бот читает ТОЛЬКО из таблицы `events`**

## 🛠️ Сервисы

### `UnifiedEventsService`

Основной сервис для работы с событиями:

```python
from utils.unified_events_service import UnifiedEventsService

events_service = UnifiedEventsService(engine)

# Поиск событий
events = events_service.search_events_today("bali")

# Создание пользовательского события
event_id = events_service.create_user_event(
    organizer_id=123456,
    title="Мое событие",
    description="Описание",
    starts_at_utc=datetime.utcnow(),
    city="bali",
    lat=-8.6500,
    lng=115.2167,
    location_name="Место"
)

# Сохранение парсерного события
event_id = events_service.save_parser_event(
    source="baliforum",
    external_id="bf_123",
    title="Событие с форума",
    description="Описание",
    starts_at_utc=datetime.utcnow(),
    city="bali",
    lat=-8.6500,
    lng=115.2167,
    location_name="Место"
)
```

## 📊 Текущее состояние

- **events**: 22 события (единая таблица)
- **events_parser**: 5 событий (парсеры)
- **events_user**: 17 событий (пользователи)

### По источникам в events:
- user: 17 событий
- kudago: 2 события
- baliforum: 2 события
- test_parser: 1 событие

### По городам в events:
- bali: 17 событий
- moscow: 4 события
- spb: 1 событие

## ✅ Преимущества

1. **Простота** - бот читает из одной таблицы
2. **Разделение** - четкое разделение парсерных и пользовательских событий
3. **Синхронизация** - автоматическая синхронизация между таблицами
4. **Производительность** - нет сложных UNION запросов
5. **Масштабируемость** - легко добавлять новые источники

## 🚀 Использование

Все компоненты обновлены для работы с единой архитектурой:

- `bot_enhanced_v3.py` - использует `UnifiedEventsService`
- `utils/parser_integration.py` - использует `UnifiedEventsService`
- `check_parser_flow.py` - использует `UnifiedEventsService`

Архитектура готова к продакшену! 🎉
