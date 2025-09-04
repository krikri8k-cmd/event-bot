-- Индексы для таблицы events
-- Быстрые запросы по геолокации, времени и источнику

-- Геолокация (уже есть, но для полноты)
CREATE INDEX IF NOT EXISTS idx_events_lat_lon ON events(lat, lng);

-- Время начала события
CREATE INDEX IF NOT EXISTS idx_events_starts_at ON events(starts_at);

-- Источник события
CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);

-- Уникальный индекс для дедупликации
CREATE UNIQUE INDEX IF NOT EXISTS ux_events_title_start_venue
ON events (lower(title), starts_at, lower(coalesce(location_name,'')));

-- Индекс для поиска по времени создания
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);
