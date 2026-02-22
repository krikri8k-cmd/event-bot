-- Мультиязычность: users.language_code NOT NULL, DEFAULT 'ru'
-- Идемпотентная миграция

-- 1. Проставить всем существующим пользователям с NULL
UPDATE users SET language_code = 'ru' WHERE language_code IS NULL;

-- 2. NOT NULL
ALTER TABLE users
ALTER COLUMN language_code SET NOT NULL;

-- 3. DEFAULT для новых записей
ALTER TABLE users
ALTER COLUMN language_code SET DEFAULT 'ru';

COMMENT ON COLUMN users.language_code IS 'Код языка: ru или en, по умолчанию ru';
