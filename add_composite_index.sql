-- Добавляем составной индекс для фильтрации по городу и стране
CREATE INDEX IF NOT EXISTS idx_events_city_country ON events (LOWER(city), country);
