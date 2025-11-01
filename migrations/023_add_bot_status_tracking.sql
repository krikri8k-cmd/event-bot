-- Migration: Добавление отслеживания статуса бота в группе
-- Дата: 2025-11-01
-- Описание: Добавляет поля для отслеживания, был ли бот удален из группы

-- Добавляем колонку bot_status для отслеживания статуса бота в группе
ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS bot_status VARCHAR(20) DEFAULT 'active';

-- Добавляем колонку bot_removed_at для хранения времени удаления бота
ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS bot_removed_at TIMESTAMP WITH TIME ZONE;

-- Создаем индекс для быстрого поиска по статусу
CREATE INDEX IF NOT EXISTS idx_chat_settings_bot_status ON chat_settings(bot_status) WHERE bot_status IS NOT NULL;

-- Комментарии к колонкам
COMMENT ON COLUMN chat_settings.bot_status IS 'Статус бота в группе: active (активен), removed (удален), inactive (неактивен)';
COMMENT ON COLUMN chat_settings.bot_removed_at IS 'Дата и время, когда бот был удален из группы';

