-- Миграция 23: Изменение типа starts_at в events_community на TIMESTAMP WITHOUT TIME ZONE
-- Это позволяет сохранять время как указал пользователь, БЕЗ конвертации в UTC
-- В Community режиме пользователь сам указывает город и время, значит он уже учел часовой пояс

DO $$
BEGIN
    -- Меняем тип starts_at на TIMESTAMP WITHOUT TIME ZONE
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name='events_community' 
        AND column_name='starts_at' 
        AND data_type='timestamp with time zone'
    ) THEN
        -- Сначала конвертируем существующие данные: берем только дату и время, без timezone
        ALTER TABLE events_community 
            ALTER COLUMN starts_at TYPE TIMESTAMP WITHOUT TIME ZONE 
            USING starts_at AT TIME ZONE 'UTC';
        
        -- Обновляем комментарий
        COMMENT ON COLUMN events_community.starts_at IS 
            'Дата и время начала события (БЕЗ конвертации в UTC - как указал пользователь)';
    END IF;
END$$;

-- Обновляем индекс (если нужно)
DROP INDEX IF EXISTS idx_events_community_starts_at;
CREATE INDEX IF NOT EXISTS idx_events_community_starts_at ON events_community(starts_at);
