-- Создаем архивные таблицы для событий (world и community)

-- Архив основной таблицы events
CREATE TABLE IF NOT EXISTS events_archive (
    id INTEGER PRIMARY KEY,
    -- Копируем ключевые поля для отчетности
    source VARCHAR(64),
    external_id VARCHAR(64),
    title VARCHAR(120) NOT NULL,
    description TEXT,
    time_local VARCHAR(16),
    date_local VARCHAR(16),
    city VARCHAR(64),
    country VARCHAR(64),
    venue VARCHAR(255),
    address VARCHAR(255),
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    url TEXT,
    price VARCHAR(64),
    organizer_id BIGINT,
    organizer_username VARCHAR(255),
    created_at_utc TIMESTAMPTZ,
    updated_at_utc TIMESTAMPTZ,
    archived_at_utc TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_archive_organizer ON events_archive(organizer_id);
CREATE INDEX IF NOT EXISTS idx_events_archive_archived_at ON events_archive(archived_at_utc);

-- Архив таблицы событий сообществ
CREATE TABLE IF NOT EXISTS events_community_archive (
    id INTEGER PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    organizer_id BIGINT,
    organizer_username VARCHAR(255),
    admin_id BIGINT,
    admin_ids TEXT,
    admin_count INTEGER,
    title VARCHAR(255) NOT NULL,
    starts_at TIMESTAMPTZ,
    description TEXT,
    city VARCHAR(64),
    location_name VARCHAR(255),
    location_url TEXT,
    created_at TIMESTAMPTZ,
    status VARCHAR(32),
    archived_at_utc TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_community_archive_chat ON events_community_archive(chat_id);
CREATE INDEX IF NOT EXISTS idx_events_community_archive_organizer ON events_community_archive(organizer_id);
CREATE INDEX IF NOT EXISTS idx_events_community_archive_archived_at ON events_community_archive(archived_at_utc);


