-- Миграция 33: Добавление поля event_id в таблицу bot_messages
-- Это позволяет точно отслеживать, для какого события было отправлено напоминание

ALTER TABLE bot_messages 
ADD COLUMN IF NOT EXISTS event_id INTEGER;

-- Создаем индекс для быстрого поиска напоминаний по event_id
CREATE INDEX IF NOT EXISTS idx_bot_messages_event_id ON bot_messages(event_id) WHERE event_id IS NOT NULL;

-- Создаем составной индекс для проверки дубликатов напоминаний
CREATE INDEX IF NOT EXISTS idx_bot_messages_event_tag_created 
ON bot_messages(event_id, tag, created_at) 
WHERE event_id IS NOT NULL AND tag IN ('reminder', 'event_start');

COMMENT ON COLUMN bot_messages.event_id IS 'ID события, для которого было отправлено сообщение (для reminder и event_start)';

