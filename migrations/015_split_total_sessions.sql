-- Добавляем раздельные счетчики сессий World/Community
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS total_sessions_world INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_sessions_community INTEGER DEFAULT 0;

-- Для совместимости оставляем существующий total_sessions как есть
-- (новые инкременты будут обновлять и суммарный, и раздельные)

-- Индексы не требуются, так как поля используются только для чтения/обновления по id


