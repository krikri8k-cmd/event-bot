-- Миграция 2: Добавление таблиц для трекинга сообщений бота

-- 1. Таблица для хранения ID всех сообщений бота в чатах
CREATE TABLE IF NOT EXISTS bot_messages (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    tag VARCHAR(50) DEFAULT 'service',  -- panel, service, notification, etc
    deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Индексы для быстрого поиска
    CONSTRAINT unique_chat_message UNIQUE(chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_bot_messages_chat_id ON bot_messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_bot_messages_deleted ON bot_messages(deleted);
CREATE INDEX IF NOT EXISTS idx_bot_messages_tag ON bot_messages(tag);

COMMENT ON TABLE bot_messages IS 'Трекинг всех сообщений бота в групповых чатах для функции "Спрятать бота"';
COMMENT ON COLUMN bot_messages.tag IS 'Тип сообщения: panel (главная панель), service (служебное), notification (уведомление)';
COMMENT ON COLUMN bot_messages.deleted IS 'Флаг удаленного сообщения';

-- 2. Таблица для настроек чата
CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id BIGINT PRIMARY KEY,
    last_panel_message_id BIGINT,  -- ID последнего панель-поста
    muted BOOLEAN DEFAULT FALSE,   -- Флаг "бот скрыт" (для будущего использования)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE chat_settings IS 'Настройки групповых чатов';
COMMENT ON COLUMN chat_settings.last_panel_message_id IS 'ID главного панель-поста (редактируется вместо создания новых)';
COMMENT ON COLUMN chat_settings.muted IS 'Флаг "бот скрыт" (резерв для будущего функционала)';

-- 3. Триггер для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_chat_settings_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_chat_settings_updated_at ON chat_settings;
CREATE TRIGGER trigger_chat_settings_updated_at
    BEFORE UPDATE ON chat_settings
    FOR EACH ROW
    EXECUTE FUNCTION update_chat_settings_updated_at();

