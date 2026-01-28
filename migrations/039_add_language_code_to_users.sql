-- Добавление поля language_code в таблицу users для поддержки мультиязычности
-- Идемпотентная миграция

ALTER TABLE users
ADD COLUMN IF NOT EXISTS language_code VARCHAR(5);

COMMENT ON COLUMN users.language_code IS 'Код языка пользователя: ru, en или NULL (если не выбран)';

-- Индекс для быстрого поиска пользователей по языку (опционально, для аналитики)
CREATE INDEX IF NOT EXISTS idx_users_language_code ON users(language_code) WHERE language_code IS NOT NULL;
