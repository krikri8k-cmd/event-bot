-- Миграция: объединение events_parser и events_user в таблицу events
-- Безопасная миграция с сохранением данных и откатом

BEGIN;

-- 1. Добавляем недостающие колонки в events
ALTER TABLE events 
  ADD COLUMN IF NOT EXISTS country VARCHAR(8),
  ADD COLUMN IF NOT EXISTS city VARCHAR(64),
  ADD COLUMN IF NOT EXISTS venue_name VARCHAR(255),
  ADD COLUMN IF NOT EXISTS address TEXT;

-- 2. Создаем индексы для новых полей
CREATE INDEX IF NOT EXISTS idx_events_country ON events(country);
CREATE INDEX IF NOT EXISTS idx_events_city ON events(city);
CREATE INDEX IF NOT EXISTS idx_events_country_city ON events(country, city);

-- 3. Проверяем количество записей перед миграцией
DO $$
DECLARE
    parser_count INTEGER;
    user_count INTEGER;
    events_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO parser_count FROM events_parser;
    SELECT COUNT(*) INTO user_count FROM events_user;
    SELECT COUNT(*) INTO events_count FROM events;
    
    RAISE NOTICE 'До миграции: events_parser=%, events_user=%, events=%', 
                 parser_count, user_count, events_count;
END $$;

-- 4. Мигрируем events_parser → events
-- Устанавливаем source для событий от парсеров
INSERT INTO events (
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
FROM events_parser
WHERE NOT EXISTS (
    -- Избегаем дубликатов по source + external_id
    SELECT 1 FROM events e 
    WHERE e.source = events_parser.source 
    AND e.external_id = events_parser.external_id
);

-- 5. Мигрируем events_user → events
-- Устанавливаем source='user' для пользовательских событий
INSERT INTO events (
    source, organizer_id, organizer_username, title, description,
    starts_at, ends_at, url, location_name, location_url, lat, lng,
    country, city, max_participants, current_participants, participants_ids,
    status, community_name, community_link, created_at_utc, updated_at_utc
)
SELECT 
    'user', organizer_id, organizer_username, title, description,
    starts_at, ends_at, url, location_name, location_url, lat, lng,
    country, city, max_participants, current_participants, participants_ids,
    status, community_name, community_link, created_at_utc, updated_at_utc
FROM events_user
WHERE NOT EXISTS (
    -- Избегаем дубликатов по organizer_id + title + starts_at
    SELECT 1 FROM events e 
    WHERE e.source = 'user'
    AND e.organizer_id = events_user.organizer_id
    AND e.title = events_user.title
    AND e.starts_at = events_user.starts_at
);

-- 6. Проверяем результат миграции
DO $$
DECLARE
    parser_count INTEGER;
    user_count INTEGER;
    events_count INTEGER;
    migrated_parser INTEGER;
    migrated_user INTEGER;
BEGIN
    SELECT COUNT(*) INTO parser_count FROM events_parser;
    SELECT COUNT(*) INTO user_count FROM events_user;
    SELECT COUNT(*) INTO events_count FROM events;
    
    -- Подсчитываем мигрированные записи
    SELECT COUNT(*) INTO migrated_parser FROM events WHERE source != 'user';
    SELECT COUNT(*) INTO migrated_user FROM events WHERE source = 'user';
    
    RAISE NOTICE 'После миграции: events_parser=%, events_user=%, events=%', 
                 parser_count, user_count, events_count;
    RAISE NOTICE 'Мигрировано: parser_events=%, user_events=%', 
                 migrated_parser, migrated_user;
                 
    -- Проверяем целостность
    IF parser_count + user_count != events_count THEN
        RAISE WARNING 'ВНИМАНИЕ: Количество записей не совпадает!';
    END IF;
END $$;

-- 7. Создаем резервные копии таблиц (опционально)
-- CREATE TABLE events_parser_backup AS SELECT * FROM events_parser;
-- CREATE TABLE events_user_backup AS SELECT * FROM events_user;

COMMIT;

-- 8. Информация для следующих шагов
SELECT 
    'Миграция завершена успешно!' as status,
    (SELECT COUNT(*) FROM events WHERE source != 'user') as parser_events,
    (SELECT COUNT(*) FROM events WHERE source = 'user') as user_events,
    (SELECT COUNT(*) FROM events) as total_events;
