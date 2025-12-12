-- Миграция 22: Добавление столбцов для участников в events_community
-- Оптимизация: храним участников прямо в таблице событий вместо отдельной таблицы

-- 1. Добавляем столбцы для участников
ALTER TABLE events_community 
    ADD COLUMN IF NOT EXISTS participants_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS participants_ids JSONB DEFAULT '[]'::jsonb;

-- 2. Создаем индекс для быстрого поиска по участникам (GIN индекс для JSONB)
CREATE INDEX IF NOT EXISTS idx_events_community_participants_ids 
    ON events_community USING GIN (participants_ids);

-- 3. Миграция данных из community_event_participants (если таблица существует)
-- Используем отдельный блок для миграции данных
DO $migrate_participants$
DECLARE
    event_record RECORD;
    participant_count INTEGER;
    participant_ids JSONB;
BEGIN
    -- Проверяем, существует ли таблица community_event_participants
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_name = 'community_event_participants'
    ) THEN
        -- Обновляем каждое событие данными из таблицы участников
        FOR event_record IN 
            SELECT DISTINCT event_id FROM community_event_participants
        LOOP
            -- Получаем количество участников
            SELECT COUNT(*) INTO participant_count
            FROM community_event_participants
            WHERE event_id = event_record.event_id;
            
            -- Получаем массив участников с их данными
            SELECT COALESCE(jsonb_agg(
                jsonb_build_object(
                    'user_id', user_id,
                    'username', username,
                    'created_at', created_at
                ) ORDER BY created_at
            ), '[]'::jsonb) INTO participant_ids
            FROM community_event_participants
            WHERE event_id = event_record.event_id;
            
            -- Обновляем событие
            UPDATE events_community
            SET 
                participants_count = participant_count,
                participants_ids = participant_ids
            WHERE id = event_record.event_id;
        END LOOP;
        
        RAISE NOTICE 'Миграция данных из community_event_participants завершена';
    ELSE
        RAISE NOTICE 'Таблица community_event_participants не найдена, пропускаем миграцию данных';
    END IF;
END $migrate_participants$;

-- 4. Комментарии
COMMENT ON COLUMN events_community.participants_count IS 'Количество участников события';
COMMENT ON COLUMN events_community.participants_ids IS 'JSONB массив участников: [{"user_id": 123, "username": "user", "created_at": "2025-01-01T00:00:00Z"}]';

