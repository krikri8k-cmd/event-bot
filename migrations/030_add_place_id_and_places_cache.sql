-- Добавление place_id в таблицу events и создание кэша мест

-- 1. Добавляем place_id в таблицу events
ALTER TABLE events ADD COLUMN IF NOT EXISTS place_id TEXT;

-- Индекс для быстрого поиска по place_id
CREATE INDEX IF NOT EXISTS idx_events_place_id ON events(place_id) WHERE place_id IS NOT NULL;

-- 2. Создаем таблицу для кэширования place_id → name
CREATE TABLE IF NOT EXISTS places_cache (
    place_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индекс для поиска по координатам (если нужно будет искать по координатам)
CREATE INDEX IF NOT EXISTS idx_places_cache_coords ON places_cache(lat, lng) WHERE lat IS NOT NULL AND lng IS NOT NULL;

-- Комментарии
COMMENT ON COLUMN events.place_id IS 'Google Place ID для получения названия места через Places API';
COMMENT ON TABLE places_cache IS 'Кэш для place_id → название места, чтобы не делать повторные запросы к Places API';

