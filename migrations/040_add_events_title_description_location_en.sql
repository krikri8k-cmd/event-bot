-- Мультиязычность событий (RU/EN): колонки для английского перевода
-- Существующие title, description, location_name считаем русскими

ALTER TABLE events
ADD COLUMN IF NOT EXISTS title_en VARCHAR(255),
ADD COLUMN IF NOT EXISTS description_en TEXT,
ADD COLUMN IF NOT EXISTS location_name_en VARCHAR(255);

COMMENT ON COLUMN events.title_en IS 'English translation of title for display when user language is en';
COMMENT ON COLUMN events.description_en IS 'English translation of description';
COMMENT ON COLUMN events.location_name_en IS 'English translation of location name';
