-- Добавляем поле для отслеживания времени последней сессии World
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_session_world_at_utc TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN users.last_session_world_at_utc IS 'Время последней сессии пользователя в World версии (используется для предотвращения двойного подсчета при частых командах)';

