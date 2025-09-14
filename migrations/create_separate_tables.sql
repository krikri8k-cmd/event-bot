-- Создание отдельных таблиц для парсера и пользователей
-- Безопасная миграция с сохранением данных

-- 1. Таблица для событий от парсеров
CREATE TABLE IF NOT EXISTS events_parser (
    id SERIAL PRIMARY KEY,
    source VARCHAR(64) NOT NULL,                    -- 'baliforum', 'kudago', etc
    external_id VARCHAR(64) NOT NULL,               -- ID из источника
    title VARCHAR(120) NOT NULL,
    description TEXT,
    starts_at TIMESTAMP WITH TIME ZONE,
    ends_at TIMESTAMP WITH TIME ZONE,
    url TEXT,
    location_name VARCHAR(255),
    location_url TEXT,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    country VARCHAR(8),                             -- 'ID', 'RU', etc
    city VARCHAR(64),                               -- 'moscow', 'spb', 'ubud', etc
    venue_name VARCHAR(255),                        -- название места
    address TEXT,                                   -- адрес
    community_name VARCHAR(120),                    -- название сообщества
    community_link TEXT,                            -- ссылка на сообщество
    created_at_utc TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at_utc TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Уникальность по источнику и внешнему ID
    UNIQUE(source, external_id)
);

-- 2. Таблица для пользовательских событий  
CREATE TABLE IF NOT EXISTS events_user (
    id SERIAL PRIMARY KEY,
    organizer_id BIGINT,                            -- ID пользователя-организатора
    organizer_username VARCHAR(255),                -- username организатора
    title VARCHAR(120) NOT NULL,
    description TEXT,
    starts_at TIMESTAMP WITH TIME ZONE,
    ends_at TIMESTAMP WITH TIME ZONE,
    url TEXT,
    location_name VARCHAR(255),
    location_url TEXT,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    country VARCHAR(8),                             -- страна пользователя
    city VARCHAR(64),                               -- город пользователя
    max_participants INTEGER,
    current_participants INTEGER DEFAULT 0,
    participants_ids TEXT,                          -- список участников
    status VARCHAR(16) DEFAULT 'open',              -- 'open', 'closed', 'cancelled'
    community_name VARCHAR(120),
    community_link TEXT,
    created_at_utc TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at_utc TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Мягкий дедуп для одного организатора на одно время/заголовок
    UNIQUE(organizer_id, title, starts_at)
);

-- 3. Индексы для events_parser
CREATE INDEX IF NOT EXISTS idx_events_parser_source ON events_parser (source);
CREATE INDEX IF NOT EXISTS idx_events_parser_country_city ON events_parser (country, city);
CREATE INDEX IF NOT EXISTS idx_events_parser_starts_at ON events_parser (starts_at);
CREATE INDEX IF NOT EXISTS idx_events_parser_lat_lng ON events_parser (lat, lng);
-- Простой индекс по координатам (без earthdistance)
CREATE INDEX IF NOT EXISTS idx_events_parser_coords ON events_parser (lat, lng) WHERE lat IS NOT NULL AND lng IS NOT NULL;

-- 4. Индексы для events_user
CREATE INDEX IF NOT EXISTS idx_events_user_organizer ON events_user (organizer_id);
CREATE INDEX IF NOT EXISTS idx_events_user_country_city ON events_user (country, city);
CREATE INDEX IF NOT EXISTS idx_events_user_starts_at ON events_user (starts_at);
CREATE INDEX IF NOT EXISTS idx_events_user_status ON events_user (status);
CREATE INDEX IF NOT EXISTS idx_events_user_lat_lng ON events_user (lat, lng);
-- Простой индекс по координатам (без earthdistance)
CREATE INDEX IF NOT EXISTS idx_events_user_coords ON events_user (lat, lng) WHERE lat IS NOT NULL AND lng IS NOT NULL;

-- 5. Комментарии для документации
COMMENT ON TABLE events_parser IS 'События от парсеров (baliforum, kudago, etc)';
COMMENT ON TABLE events_user IS 'Пользовательские события (созданные пользователями)';

COMMENT ON COLUMN events_parser.source IS 'Источник события (baliforum, kudago, etc)';
COMMENT ON COLUMN events_parser.external_id IS 'Уникальный ID из источника';
COMMENT ON COLUMN events_parser.country IS 'Код страны (ID, RU, etc)';
COMMENT ON COLUMN events_parser.city IS 'Город (moscow, spb, ubud, etc)';

COMMENT ON COLUMN events_user.organizer_id IS 'ID пользователя-организатора';
COMMENT ON COLUMN events_user.country IS 'Страна пользователя';
COMMENT ON COLUMN events_user.city IS 'Город пользователя';
