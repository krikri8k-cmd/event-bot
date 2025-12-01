-- Миграция 028: Добавление полей для отслеживания награды за добавление бота в чат
-- Награда: 150 ракет за добавление бота в чат (один раз на чат)
-- Используем существующую таблицу chat_settings вместо создания новой

-- Добавляем поля в chat_settings для отслеживания награды
ALTER TABLE chat_settings 
ADD COLUMN IF NOT EXISTS added_by_user_id BIGINT,
ADD COLUMN IF NOT EXISTS rockets_awarded_at TIMESTAMP WITH TIME ZONE;

-- Создаем индекс для быстрого поиска по пользователю
CREATE INDEX IF NOT EXISTS idx_chat_settings_added_by_user_id ON chat_settings(added_by_user_id);

COMMENT ON COLUMN chat_settings.added_by_user_id IS 'ID пользователя, который добавил бота (для награды)';
COMMENT ON COLUMN chat_settings.rockets_awarded_at IS 'Дата и время начисления награды за добавление бота в чат';

