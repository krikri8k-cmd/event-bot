-- Добавление колонок аналитики в таблицу users
-- Для лучшего понимания активности пользователей

-- Количество сессий (заходов в бота)
ALTER TABLE users ADD COLUMN IF NOT EXISTS total_sessions INTEGER DEFAULT 0;

-- Общее количество принятых заданий
ALTER TABLE users ADD COLUMN IF NOT EXISTS tasks_accepted_total INTEGER DEFAULT 0;

-- Общее количество выполненных заданий
ALTER TABLE users ADD COLUMN IF NOT EXISTS tasks_completed_total INTEGER DEFAULT 0;

-- Общее количество созданных событий
ALTER TABLE users ADD COLUMN IF NOT EXISTS events_created_total INTEGER DEFAULT 0;

-- Добавляем комментарии к колонкам
COMMENT ON COLUMN users.total_sessions IS 'Общее количество сессий (заходов в бота)';
COMMENT ON COLUMN users.tasks_accepted_total IS 'Общее количество принятых заданий';
COMMENT ON COLUMN users.tasks_completed_total IS 'Общее количество выполненных заданий';
COMMENT ON COLUMN users.events_created_total IS 'Общее количество созданных событий';

-- Создаем индексы для быстрого поиска активных пользователей (опционально)
CREATE INDEX IF NOT EXISTS idx_users_total_sessions ON users(total_sessions);
CREATE INDEX IF NOT EXISTS idx_users_events_created_total ON users(events_created_total);
CREATE INDEX IF NOT EXISTS idx_users_tasks_completed_total ON users(tasks_completed_total);

