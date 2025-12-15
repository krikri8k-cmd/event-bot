-- Миграция 23: Изменение типа starts_at в events_community на TIMESTAMP WITHOUT TIME ZONE
-- Это позволяет сохранять время как указал пользователь, БЕЗ конвертации в UTC
-- В Community режиме пользователь сам указывает город и время, значит он уже учел часовой пояс

-- Меняем тип starts_at на TIMESTAMP WITHOUT TIME ZONE
-- Сначала конвертируем существующие данные: берем только дату и время, без timezone
ALTER TABLE events_community 
    ALTER COLUMN starts_at TYPE TIMESTAMP WITHOUT TIME ZONE 
    USING starts_at AT TIME ZONE 'UTC';

-- Обновляем комментарий
COMMENT ON COLUMN events_community.starts_at IS 
    'Дата и время начала события (БЕЗ конвертации в UTC - как указал пользователь)';

-- Обновляем индекс (если нужно)
DROP INDEX IF EXISTS idx_events_community_starts_at;
CREATE INDEX IF NOT EXISTS idx_events_community_starts_at ON events_community(starts_at);
