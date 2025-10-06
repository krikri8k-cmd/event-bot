-- Добавляем поле chat_id в таблицу events_user для групповых чатов
ALTER TABLE events_user ADD COLUMN chat_id BIGINT;

-- Создаем индекс для быстрого поиска по chat_id
CREATE INDEX idx_events_user_chat_id ON events_user(chat_id);

-- Добавляем поле chat_id в основную таблицу events для совместимости
ALTER TABLE events ADD COLUMN chat_id BIGINT;

-- Создаем индекс для быстрого поиска по chat_id
CREATE INDEX idx_events_chat_id ON events(chat_id);
