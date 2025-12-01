-- Миграция 028: Создание таблицы для отслеживания добавлений бота в группы
-- Награда: 500 ракет за добавление бота в чат (один раз на чат)

CREATE TABLE IF NOT EXISTS bot_group_additions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    rockets_awarded INTEGER DEFAULT 500,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_bot_group_additions_user_chat UNIQUE (user_id, chat_id)
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_bot_group_additions_user_id ON bot_group_additions(user_id);
CREATE INDEX IF NOT EXISTS idx_bot_group_additions_chat_id ON bot_group_additions(chat_id);
CREATE INDEX IF NOT EXISTS idx_bot_group_additions_added_at ON bot_group_additions(added_at);

COMMENT ON TABLE bot_group_additions IS 'Отслеживание добавлений бота в группы для начисления наград';
COMMENT ON COLUMN bot_group_additions.user_id IS 'ID пользователя, который добавил бота';
COMMENT ON COLUMN bot_group_additions.chat_id IS 'ID чата, в который был добавлен бот';
COMMENT ON COLUMN bot_group_additions.rockets_awarded IS 'Количество начисленных ракет (по умолчанию 500)';
COMMENT ON COLUMN bot_group_additions.added_at IS 'Дата и время добавления бота в чат';

