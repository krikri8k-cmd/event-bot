-- Миграция: Добавление колонки total_events в chat_settings
-- Описание: Отслеживание общего количества событий, созданных в чате через бота

-- Добавляем колонку total_events
ALTER TABLE chat_settings
ADD COLUMN IF NOT EXISTS total_events INTEGER DEFAULT 0 NOT NULL;

-- Создаем индекс для быстрого поиска (опционально, если нужна сортировка)
CREATE INDEX IF NOT EXISTS idx_chat_settings_total_events ON chat_settings(total_events);

-- Комментарий к колонке
COMMENT ON COLUMN chat_settings.total_events IS 'Общее количество событий, созданных в этом чате через бота';

-- Backfill: подсчитываем существующие события для каждого чата
UPDATE chat_settings cs
SET total_events = (
    SELECT COUNT(*)
    FROM events_community ec
    WHERE ec.chat_id = cs.chat_id
)
WHERE EXISTS (
    SELECT 1
    FROM events_community ec
    WHERE ec.chat_id = cs.chat_id
);

