-- УПРОЩЕННАЯ АРХИТЕКТУРА СОБЫТИЙ
-- 3 основные таблицы + timezone логика

-- 1. СОБЫТИЯ ОТ ПАРСЕРОВ
-- (BaliForum, KudaGo, Meetup, AI)
CREATE TABLE IF NOT EXISTS events_parser (
    id SERIAL PRIMARY KEY,
    source VARCHAR(64) NOT NULL,           -- 'baliforum', 'kudago', 'meetup', 'ai'
    external_id VARCHAR(64) NOT NULL,      -- ID из внешнего источника
    title VARCHAR(120) NOT NULL,
    description TEXT,
    starts_at TIMESTAMPTZ NOT NULL,        -- Время в UTC
    city VARCHAR(64) NOT NULL,             -- 'bali', 'moscow', 'spb'
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    location_name VARCHAR(255),
    location_url TEXT,
    url TEXT,                              -- Ссылка на источник
    created_at_utc TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(source, external_id)            -- Дедупликация
);

-- 2. СОБЫТИЯ ОТ ПОЛЬЗОВАТЕЛЕЙ
CREATE TABLE IF NOT EXISTS events_user (
    id SERIAL PRIMARY KEY,
    organizer_id BIGINT NOT NULL,          -- ID пользователя Telegram
    title VARCHAR(120) NOT NULL,
    description TEXT,
    starts_at TIMESTAMPTZ NOT NULL,        -- Время в UTC
    city VARCHAR(64) NOT NULL,             -- 'bali', 'moscow', 'spb'
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    location_name VARCHAR(255),
    location_url TEXT,
    max_participants INTEGER,
    current_participants INTEGER DEFAULT 0,
    status VARCHAR(16) DEFAULT 'open',     -- 'open', 'closed', 'cancelled'
    created_at_utc TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(organizer_id, title, starts_at) -- Один пользователь не может создать одинаковые события
);

-- 3. ОБЪЕДИНЕННАЯ ТАБЛИЦА ВСЕХ СОБЫТИЙ (VIEW)
CREATE OR REPLACE VIEW events AS
SELECT 
    'parser' as source_type,
    id,
    title,
    description,
    starts_at,
    city,
    lat,
    lng,
    location_name,
    location_url,
    url as event_url,
    NULL as organizer_id,
    NULL as max_participants,
    NULL as current_participants,
    'open' as status,
    created_at_utc
FROM events_parser

UNION ALL

SELECT 
    'user' as source_type,
    id,
    title,
    description,
    starts_at,
    city,
    lat,
    lng,
    location_name,
    location_url,
    NULL as event_url,
    organizer_id,
    max_participants,
    current_participants,
    status,
    created_at_utc
FROM events_user;

-- ИНДЕКСЫ ДЛЯ ПРОИЗВОДИТЕЛЬНОСТИ
CREATE INDEX IF NOT EXISTS idx_events_parser_city_time ON events_parser (city, starts_at);
CREATE INDEX IF NOT EXISTS idx_events_parser_coords ON events_parser (lat, lng);
CREATE INDEX IF NOT EXISTS idx_events_parser_source ON events_parser (source);

CREATE INDEX IF NOT EXISTS idx_events_user_city_time ON events_user (city, starts_at);
CREATE INDEX IF NOT EXISTS idx_events_user_coords ON events_user (lat, lng);
CREATE INDEX IF NOT EXISTS idx_events_user_organizer ON events_user (organizer_id);
CREATE INDEX IF NOT EXISTS idx_events_user_status ON events_user (status);

-- ОЧИСТКА СТАРЫХ СОБЫТИЙ (вызывается из Python)
-- DELETE FROM events_parser WHERE city = 'bali' AND starts_at < NOW() - INTERVAL '1 day';
-- DELETE FROM events_user WHERE city = 'bali' AND starts_at < NOW() - INTERVAL '1 day';

-- ПРИМЕРЫ ЗАПРОСОВ

-- 1. Поиск сегодняшних событий в городе (вызывается из Python с timezone)
-- SELECT * FROM events 
-- WHERE city = 'bali' 
-- AND starts_at >= $1::timestamptz  -- начало дня в UTC
-- AND starts_at < $2::timestamptz   -- начало завтра в UTC
-- ORDER BY starts_at;

-- 2. Поиск событий в радиусе (вызывается из Python с координатами)
-- SELECT *, 
--        earth_distance(ll_to_earth($1, $2), ll_to_earth(lat, lng)) / 1000 as distance_km
-- FROM events 
-- WHERE city = 'bali'
-- AND starts_at >= $3::timestamptz
-- AND starts_at < $4::timestamptz
-- AND (lat IS NULL OR earth_distance(ll_to_earth($1, $2), ll_to_earth(lat, lng)) <= $5 * 1000)
-- ORDER BY starts_at;

-- 3. Очистка старых событий
-- SELECT cleanup_old_events('bali');
