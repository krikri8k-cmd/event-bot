-- Миграция 27: Добавление поля is_banned в таблицу users

-- Добавляем поле is_banned в таблицу users
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE;

-- Создаем индекс для быстрой проверки бана
CREATE INDEX IF NOT EXISTS idx_users_is_banned ON users(is_banned) WHERE is_banned = TRUE;

-- Синхронизируем существующие баны из banned_users в users
UPDATE users
SET is_banned = TRUE
WHERE id IN (
    SELECT user_id 
    FROM banned_users 
    WHERE is_active = TRUE 
    AND (expires_at IS NULL OR expires_at > NOW())
);

COMMENT ON COLUMN users.is_banned IS 'Флаг бана пользователя (синхронизируется с banned_users)';

