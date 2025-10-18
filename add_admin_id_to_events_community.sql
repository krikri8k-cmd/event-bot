-- Добавление поля admin_id в таблицу events_community
ALTER TABLE events_community 
ADD COLUMN IF NOT EXISTS admin_id BIGINT;

-- Создаем индекс для быстрого поиска по admin_id
CREATE INDEX IF NOT EXISTS idx_events_community_admin_id ON events_community(admin_id);
