-- Язык группы по умолчанию для мультиязычности Community
-- Идемпотентная миграция

ALTER TABLE chat_settings
ADD COLUMN IF NOT EXISTS default_language VARCHAR(5) NOT NULL DEFAULT 'ru';

COMMENT ON COLUMN chat_settings.default_language IS 'Язык по умолчанию для сообщений в группе: ru или en';
