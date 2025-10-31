-- Migration: Добавить поле last_session_community_at_utc в таблицу users
-- Дата: 2025-10-31
-- Описание: Добавляет поле для отслеживания времени последней сессии в Community (групповых чатах)

-- Добавляем колонку last_session_community_at_utc
ALTER TABLE users
ADD COLUMN IF NOT EXISTS last_session_community_at_utc TIMESTAMP WITH TIME ZONE;

-- Комментарий к колонке
COMMENT ON COLUMN users.last_session_community_at_utc IS 'Время последней сессии пользователя в Community (групповых чатах). Используется для отслеживания активности пользователя в группах.';

