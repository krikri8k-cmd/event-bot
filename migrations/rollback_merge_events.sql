-- Откат миграции: разделение events обратно на events_parser и events_user
-- ВНИМАНИЕ: Этот скрипт удалит данные, добавленные после миграции!

BEGIN;

-- 1. Проверяем текущее состояние
DO $$
DECLARE
    events_count INTEGER;
    parser_count INTEGER;
    user_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO events_count FROM events;
    SELECT COUNT(*) INTO parser_count FROM events WHERE source != 'user';
    SELECT COUNT(*) INTO user_count FROM events WHERE source = 'user';
    
    RAISE NOTICE 'До отката: events=%, parser_events=%, user_events=%', 
                 events_count, parser_count, user_count;
END $$;

-- 2. Восстанавливаем events_parser из events
-- Удаляем существующие данные
DELETE FROM events_parser;

-- Вставляем данные из events (исключая user события)
INSERT INTO events_parser (
    source, external_id, title, description, starts_at, ends_at,
    url, location_name, location_url, lat, lng,
    country, city, venue_name, address,
    community_name, community_link, created_at_utc, updated_at_utc
)
SELECT 
    source, external_id, title, description, starts_at, ends_at,
    url, location_name, location_url, lat, lng,
    country, city, venue_name, address,
    community_name, community_link, created_at_utc, updated_at_utc
FROM events 
WHERE source != 'user' AND source IS NOT NULL;

-- 3. Восстанавливаем events_user из events
-- Удаляем существующие данные
DELETE FROM events_user;

-- Вставляем данные из events (только user события)
INSERT INTO events_user (
    organizer_id, organizer_username, title, description,
    starts_at, ends_at, url, location_name, location_url, lat, lng,
    country, city, max_participants, current_participants, participants_ids,
    status, community_name, community_link, created_at_utc, updated_at_utc
)
SELECT 
    organizer_id, organizer_username, title, description,
    starts_at, ends_at, url, location_name, location_url, lat, lng,
    country, city, max_participants, current_participants, participants_ids,
    status, community_name, community_link, created_at_utc, updated_at_utc
FROM events 
WHERE source = 'user';

-- 4. Удаляем мигрированные данные из events
-- Оставляем только события без source (если есть)
DELETE FROM events WHERE source IS NOT NULL;

-- 5. Удаляем добавленные колонки
ALTER TABLE events 
  DROP COLUMN IF EXISTS country,
  DROP COLUMN IF EXISTS city,
  DROP COLUMN IF EXISTS venue_name,
  DROP COLUMN IF EXISTS address;

-- 6. Удаляем индексы
DROP INDEX IF EXISTS idx_events_country;
DROP INDEX IF EXISTS idx_events_city;
DROP INDEX IF EXISTS idx_events_country_city;

-- 7. Проверяем результат отката
DO $$
DECLARE
    events_count INTEGER;
    parser_count INTEGER;
    user_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO events_count FROM events;
    SELECT COUNT(*) INTO parser_count FROM events_parser;
    SELECT COUNT(*) INTO user_count FROM events_user;
    
    RAISE NOTICE 'После отката: events=%, events_parser=%, events_user=%', 
                 events_count, parser_count, user_count;
END $$;

COMMIT;

-- 8. Информация о результате
SELECT 
    'Откат миграции завершен!' as status,
    (SELECT COUNT(*) FROM events_parser) as parser_events,
    (SELECT COUNT(*) FROM events_user) as user_events,
    (SELECT COUNT(*) FROM events) as remaining_events;
