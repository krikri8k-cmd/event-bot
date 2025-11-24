-- Миграция 26: Создание таблицы для бана пользователей

-- Таблица для хранения забаненных пользователей
CREATE TABLE IF NOT EXISTS banned_users (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE,
    username VARCHAR(255),
    first_name VARCHAR(255),
    banned_by BIGINT NOT NULL,  -- ID админа, который забанил
    reason TEXT,  -- Причина бана
    banned_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,  -- NULL = бессрочный бан
    is_active BOOLEAN DEFAULT TRUE,  -- Для возможности временного отключения бана
    
    -- Индексы для быстрого поиска
    CONSTRAINT unique_banned_user UNIQUE(user_id)
);

CREATE INDEX IF NOT EXISTS idx_banned_users_user_id ON banned_users(user_id);
CREATE INDEX IF NOT EXISTS idx_banned_users_active ON banned_users(is_active);
CREATE INDEX IF NOT EXISTS idx_banned_users_expires_at ON banned_users(expires_at);

COMMENT ON TABLE banned_users IS 'Таблица забаненных пользователей';
COMMENT ON COLUMN banned_users.user_id IS 'Telegram ID пользователя';
COMMENT ON COLUMN banned_users.banned_by IS 'ID админа, который забанил пользователя';
COMMENT ON COLUMN banned_users.reason IS 'Причина бана (опционально)';
COMMENT ON COLUMN banned_users.expires_at IS 'Дата окончания бана (NULL = бессрочный)';
COMMENT ON COLUMN banned_users.is_active IS 'Активен ли бан (можно временно отключить без удаления записи)';

