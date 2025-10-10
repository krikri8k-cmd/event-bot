-- Миграция 1: Исправление структуры events_community
-- Приведение к правильным названиям полей и добавление недостающих

-- 1. Переименование полей (если таблица создана по старой схеме)
DO $$
BEGIN
    -- Переименовываем group_id в chat_id (если существует)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='events_community' AND column_name='group_id'
    ) THEN
        ALTER TABLE events_community RENAME COLUMN group_id TO chat_id;
    END IF;
    
    -- Переименовываем creator_id в organizer_id (если существует)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='events_community' AND column_name='creator_id'
    ) THEN
        ALTER TABLE events_community RENAME COLUMN creator_id TO organizer_id;
    END IF;
    
    -- Переименовываем date в starts_at (если существует)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='events_community' AND column_name='date'
    ) THEN
        ALTER TABLE events_community RENAME COLUMN date TO starts_at;
    END IF;
END$$;

-- 2. Добавление недостающих полей
ALTER TABLE events_community 
    ADD COLUMN IF NOT EXISTS organizer_username VARCHAR(255),
    ADD COLUMN IF NOT EXISTS location_url TEXT,
    ADD COLUMN IF NOT EXISTS status VARCHAR(16) DEFAULT 'open',
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- 3. Изменение типов на TIMESTAMPTZ для правильной работы с часовыми поясами
DO $$
BEGIN
    -- Меняем тип starts_at на TIMESTAMPTZ если нужно
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='events_community' 
        AND column_name='starts_at' 
        AND data_type='timestamp without time zone'
    ) THEN
        ALTER TABLE events_community 
            ALTER COLUMN starts_at TYPE TIMESTAMPTZ 
            USING starts_at AT TIME ZONE 'UTC';
    END IF;
    
    -- Меняем тип created_at на TIMESTAMPTZ если нужно
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='events_community' 
        AND column_name='created_at' 
        AND data_type='timestamp without time zone'
    ) THEN
        ALTER TABLE events_community 
            ALTER COLUMN created_at TYPE TIMESTAMPTZ 
            USING created_at AT TIME ZONE 'UTC';
    END IF;
END$$;

-- 4. Обновление индексов
DROP INDEX IF EXISTS idx_events_community_group_id;
DROP INDEX IF EXISTS idx_events_community_date;

CREATE INDEX IF NOT EXISTS idx_events_community_chat_id ON events_community(chat_id);
CREATE INDEX IF NOT EXISTS idx_events_community_starts_at ON events_community(starts_at);
CREATE INDEX IF NOT EXISTS idx_events_community_status ON events_community(status);

-- 5. Обновление комментариев
COMMENT ON TABLE events_community IS 'События в групповых чатах (изолированно от основного бота)';
COMMENT ON COLUMN events_community.chat_id IS 'ID группового чата';
COMMENT ON COLUMN events_community.organizer_id IS 'ID создателя события';
COMMENT ON COLUMN events_community.organizer_username IS 'Username создателя';
COMMENT ON COLUMN events_community.starts_at IS 'Дата и время начала события (с часовым поясом)';
COMMENT ON COLUMN events_community.status IS 'Статус события: open, closed, cancelled';
COMMENT ON COLUMN events_community.location_url IS 'Ссылка на Google Maps';

