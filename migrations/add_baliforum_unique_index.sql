-- Миграция для добавления уникального индекса (source, external_id) 
-- и удаления проблемного ux_events_title_start_venue

-- 1. Удаляем проблемный уникальный индекс
DROP INDEX IF EXISTS ux_events_title_start_venue;

-- 2. Создаем неуникальный индекс на те же поля для производительности
CREATE INDEX IF NOT EXISTS ix_events_title_start_venue 
ON events (lower(title), starts_at, lower(COALESCE(location_name, '')));

-- 3. Добавляем уникальный индекс (source, external_id)
-- Это позволит делать идемпотентные upsert'ы
DO $$ 
BEGIN
    -- Проверяем, существует ли уже такой индекс
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE indexname = 'ux_events_source_external_id'
    ) THEN
        CREATE UNIQUE INDEX ux_events_source_external_id 
        ON events (source, external_id);
    END IF;
END $$;

-- 4. Добавляем комментарий
COMMENT ON INDEX ux_events_source_external_id IS 'Уникальный индекс для идемпотентных upsert операций по источнику и внешнему ID';
