-- ПРОДАКШЕН миграция: объединение events_parser и events_user в events
-- Включает: дедуп-ключи, CONCURRENTLY индексы, нормализацию TZ/гео, батч-миграцию

BEGIN;

-- 1. Создаем расширенную таблицу events с улучшенной структурой
DO $$
BEGIN
    -- Добавляем недостающие колонки
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='events' AND column_name='country') THEN
        ALTER TABLE events ADD COLUMN country VARCHAR(8);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='events' AND column_name='city') THEN
        ALTER TABLE events ADD COLUMN city VARCHAR(64);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='events' AND column_name='venue_name') THEN
        ALTER TABLE events ADD COLUMN venue_name VARCHAR(255);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='events' AND column_name='address') THEN
        ALTER TABLE events ADD COLUMN address TEXT;
    END IF;
    
    -- Добавляем колонку для нормализованных координат
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='events' AND column_name='geo_hash') THEN
        ALTER TABLE events ADD COLUMN geo_hash VARCHAR(32);
    END IF;
    
    -- Добавляем колонку для нормализованного времени
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='events' AND column_name='starts_at_normalized') THEN
        ALTER TABLE events ADD COLUMN starts_at_normalized TIMESTAMP WITH TIME ZONE;
    END IF;
    
    RAISE NOTICE 'Колонки добавлены в events';
END $$;

-- 2. Создаем CONCURRENTLY индексы (не блокируют таблицу)
-- Выполняем вне транзакции для CONCURRENTLY
COMMIT;

-- Создаем индексы CONCURRENTLY (выполняется отдельно)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_country 
    ON events(country) WHERE country IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_city 
    ON events(city) WHERE city IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_country_city 
    ON events(country, city) WHERE country IS NOT NULL AND city IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_geo_hash 
    ON events(geo_hash) WHERE geo_hash IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_starts_at_normalized 
    ON events(starts_at_normalized) WHERE starts_at_normalized IS NOT NULL;

-- Частичный уникальный индекс для дедупликации парсеров
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_events_parser_dedup 
    ON events(source, external_id) 
    WHERE source IS NOT NULL AND external_id IS NOT NULL;

-- Частичный уникальный индекс для дедупликации пользовательских событий
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_events_user_dedup 
    ON events(organizer_id, title, starts_at) 
    WHERE source = 'user' AND organizer_id IS NOT NULL;

-- Начинаем новую транзакцию для миграции данных
BEGIN;

-- 3. Функция для генерации geo_hash
CREATE OR REPLACE FUNCTION generate_geo_hash(lat_val FLOAT, lng_val FLOAT) 
RETURNS VARCHAR(32) AS $$
BEGIN
    IF lat_val IS NULL OR lng_val IS NULL THEN
        RETURN NULL;
    END IF;
    
    -- Нормализуем координаты до 4 знаков после запятой (~11м точности)
    RETURN encode(digest(
        (ROUND(lat_val::numeric, 4) || ',' || ROUND(lng_val::numeric, 4))::bytea, 
        'sha256'
    ), 'hex')::VARCHAR(32);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 4. Функция для нормализации времени
CREATE OR REPLACE FUNCTION normalize_timestamp(ts_val TIMESTAMP WITH TIME ZONE, tz_val VARCHAR(64)) 
RETURNS TIMESTAMP WITH TIME ZONE AS $$
BEGIN
    IF ts_val IS NULL THEN
        RETURN NULL;
    END IF;
    
    -- Если есть часовой пояс, конвертируем в UTC
    IF tz_val IS NOT NULL AND tz_val != '' THEN
        BEGIN
            RETURN ts_val AT TIME ZONE tz_val AT TIME ZONE 'UTC';
        EXCEPTION WHEN OTHERS THEN
            -- Если часовой пояс невалидный, возвращаем как есть
            RETURN ts_val;
        END;
    END IF;
    
    RETURN ts_val;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 5. Батч-миграция events_parser → events
-- Мигрируем порциями по 1000 записей для больших объемов
DO $$
DECLARE
    batch_size INTEGER := 1000;
    offset_val INTEGER := 0;
    total_count INTEGER;
    processed INTEGER := 0;
BEGIN
    -- Получаем общее количество записей
    SELECT COUNT(*) INTO total_count FROM events_parser;
    RAISE NOTICE 'Начинаем миграцию % записей из events_parser', total_count;
    
    -- Мигрируем батчами
    WHILE offset_val < total_count LOOP
        INSERT INTO events (
            source, external_id, title, description, starts_at, ends_at,
            url, location_name, location_url, lat, lng, 
            country, city, venue_name, address,
            community_name, community_link, created_at_utc, updated_at_utc,
            geo_hash, starts_at_normalized
        )
        SELECT 
            source, external_id, title, description, starts_at, ends_at,
            url, location_name, location_url, lat, lng,
            country, city, venue_name, address,
            community_name, community_link, created_at_utc, updated_at_utc,
            generate_geo_hash(lat, lng),
            normalize_timestamp(starts_at, NULL)
        FROM events_parser
        WHERE NOT EXISTS (
            SELECT 1 FROM events e 
            WHERE e.source = events_parser.source 
            AND e.external_id = events_parser.external_id
        )
        ORDER BY id
        LIMIT batch_size OFFSET offset_val;
        
        processed := processed + LEAST(batch_size, total_count - offset_val);
        offset_val := offset_val + batch_size;
        
        -- Логируем прогресс
        IF processed % 5000 = 0 OR offset_val >= total_count THEN
            RAISE NOTICE 'Мигрировано % из % записей events_parser (%.1f%%)', 
                         processed, total_count, (processed::float / total_count * 100);
        END IF;
        
        -- Небольшая пауза между батчами
        PERFORM pg_sleep(0.1);
    END LOOP;
    
    RAISE NOTICE 'Миграция events_parser завершена: % записей', processed;
END $$;

-- 6. Батч-миграция events_user → events
DO $$
DECLARE
    batch_size INTEGER := 1000;
    offset_val INTEGER := 0;
    total_count INTEGER;
    processed INTEGER := 0;
BEGIN
    -- Получаем общее количество записей
    SELECT COUNT(*) INTO total_count FROM events_user;
    RAISE NOTICE 'Начинаем миграцию % записей из events_user', total_count;
    
    -- Мигрируем батчами
    WHILE offset_val < total_count LOOP
        INSERT INTO events (
            source, organizer_id, organizer_username, title, description,
            starts_at, ends_at, url, location_name, location_url, lat, lng,
            country, city, max_participants, current_participants, participants_ids,
            status, community_name, community_link, created_at_utc, updated_at_utc,
            geo_hash, starts_at_normalized
        )
        SELECT 
            'user', organizer_id, organizer_username, title, description,
            starts_at, ends_at, url, location_name, location_url, lat, lng,
            country, city, max_participants, current_participants, participants_ids,
            status, community_name, community_link, created_at_utc, updated_at_utc,
            generate_geo_hash(lat, lng),
            normalize_timestamp(starts_at, NULL)
        FROM events_user
        WHERE NOT EXISTS (
            SELECT 1 FROM events e 
            WHERE e.source = 'user'
            AND e.organizer_id = events_user.organizer_id
            AND e.title = events_user.title
            AND e.starts_at = events_user.starts_at
        )
        ORDER BY id
        LIMIT batch_size OFFSET offset_val;
        
        processed := processed + LEAST(batch_size, total_count - offset_val);
        offset_val := offset_val + batch_size;
        
        -- Логируем прогресс
        IF processed % 5000 = 0 OR offset_val >= total_count THEN
            RAISE NOTICE 'Мигрировано % из % записей events_user (%.1f%%)', 
                         processed, total_count, (processed::float / total_count * 100);
        END IF;
        
        -- Небольшая пауза между батчами
        PERFORM pg_sleep(0.1);
    END LOOP;
    
    RAISE NOTICE 'Миграция events_user завершена: % записей', processed;
END $$;

-- 7. Обновляем существующие записи в events (нормализация)
UPDATE events SET 
    geo_hash = generate_geo_hash(lat, lng),
    starts_at_normalized = normalize_timestamp(starts_at, event_tz)
WHERE geo_hash IS NULL OR starts_at_normalized IS NULL;

-- 8. Проверка целостности данных
DO $$
DECLARE
    events_count INTEGER;
    parser_count INTEGER;
    user_count INTEGER;
    parser_migrated INTEGER;
    user_migrated INTEGER;
    duplicates INTEGER;
BEGIN
    -- Подсчитываем записи
    SELECT COUNT(*) INTO events_count FROM events;
    SELECT COUNT(*) INTO parser_count FROM events_parser;
    SELECT COUNT(*) INTO user_count FROM events_user;
    SELECT COUNT(*) INTO parser_migrated FROM events WHERE source != 'user' AND source IS NOT NULL;
    SELECT COUNT(*) INTO user_migrated FROM events WHERE source = 'user';
    
    -- Проверяем дубликаты
    SELECT COUNT(*) INTO duplicates FROM (
        SELECT source, external_id, COUNT(*) as cnt
        FROM events 
        WHERE source IS NOT NULL AND external_id IS NOT NULL
        GROUP BY source, external_id
        HAVING COUNT(*) > 1
    ) dup_check;
    
    RAISE NOTICE '=== РЕЗУЛЬТАТ МИГРАЦИИ ===';
    RAISE NOTICE 'Всего в events: %', events_count;
    RAISE NOTICE 'Мигрировано из parser: % (исходно: %)', parser_migrated, parser_count;
    RAISE NOTICE 'Мигрировано из user: % (исходно: %)', user_migrated, user_count;
    RAISE NOTICE 'Дубликатов найдено: %', duplicates;
    
    -- Проверяем целостность
    IF parser_count + user_count != events_count THEN
        RAISE WARNING 'ВНИМАНИЕ: Количество записей не совпадает!';
    END IF;
    
    IF duplicates > 0 THEN
        RAISE WARNING 'ВНИМАНИЕ: Найдены дубликаты!';
    END IF;
END $$;

-- 9. Создаем статистику для планировщика
ANALYZE events;

-- 10. Очищаем временные функции
DROP FUNCTION IF EXISTS generate_geo_hash(FLOAT, FLOAT);
DROP FUNCTION IF EXISTS normalize_timestamp(TIMESTAMP WITH TIME ZONE, VARCHAR(64));

COMMIT;

-- 11. Финальная проверка
SELECT 
    'Миграция завершена успешно!' as status,
    (SELECT COUNT(*) FROM events WHERE source != 'user' AND source IS NOT NULL) as parser_events,
    (SELECT COUNT(*) FROM events WHERE source = 'user') as user_events,
    (SELECT COUNT(*) FROM events) as total_events,
    (SELECT COUNT(*) FROM events WHERE geo_hash IS NOT NULL) as events_with_geo,
    (SELECT COUNT(*) FROM events WHERE starts_at_normalized IS NOT NULL) as events_with_normalized_time;
