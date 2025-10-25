-- Добавление поля admin_count в таблицу events_community
-- Миграция: 004_add_admin_count_to_events_community.sql

-- Добавляем новое поле admin_count
ALTER TABLE events_community 
ADD COLUMN IF NOT EXISTS admin_count INTEGER DEFAULT 0;

-- Обновляем существующие записи: считаем количество админов из admin_ids
UPDATE events_community 
SET admin_count = CASE 
    WHEN admin_ids IS NOT NULL AND admin_ids != '[]' THEN 
        (SELECT COUNT(*) FROM jsonb_array_elements_text(admin_ids::jsonb))
    ELSE 0 
END;

-- Добавляем комментарий к полю
COMMENT ON COLUMN events_community.admin_count IS 'Количество администраторов группы на момент создания события';

-- Создаем индекс для быстрого поиска по количеству админов
CREATE INDEX IF NOT EXISTS idx_events_community_admin_count ON events_community(admin_count);
