-- Добавление поля admin_ids в таблицу events_community для хранения всех админов группы
-- Миграция: 003_add_admin_ids_to_events_community.sql

-- Добавляем новое поле admin_ids (JSON)
ALTER TABLE events_community 
ADD COLUMN IF NOT EXISTS admin_ids TEXT;

-- Создаем индекс для быстрого поиска (если понадобится)
-- CREATE INDEX IF NOT EXISTS idx_events_community_admin_ids ON events_community USING GIN ((admin_ids::jsonb));

-- Мигрируем существующие данные: копируем admin_id в admin_ids как JSON массив
UPDATE events_community 
SET admin_ids = CASE 
    WHEN admin_id IS NOT NULL THEN json_build_array(admin_id)::text
    ELSE NULL 
END;

-- Добавляем комментарий к полю
COMMENT ON COLUMN events_community.admin_ids IS 'JSON массив ID всех администраторов группы на момент создания события';
