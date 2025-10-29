-- Удаление неиспользуемых колонок из таблицы users
-- events_created_ids и events_joined_ids не используются в коде
-- Данные дублируются через organizer_id в таблицах событий

-- Удаляем колонку events_created_ids
ALTER TABLE users DROP COLUMN IF EXISTS events_created_ids;

-- Удаляем колонку events_joined_ids  
ALTER TABLE users DROP COLUMN IF EXISTS events_joined_ids;

-- Добавляем комментарий для истории
COMMENT ON TABLE users IS 'Таблица пользователей - очищена от неиспользуемых колонок events_created_ids и events_joined_ids';
