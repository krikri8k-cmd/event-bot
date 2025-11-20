-- 2025_add_referral_code_to_events.sql
-- Добавляет колонку referral_code прямо в таблицу events
-- Это проще, чем отдельная таблица!

ALTER TABLE events ADD COLUMN IF NOT EXISTS referral_code TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS referral_param TEXT DEFAULT 'ref';

-- Индекс для быстрого поиска событий по реферальному коду
CREATE INDEX IF NOT EXISTS ix_events_referral_code 
    ON events (referral_code) 
    WHERE referral_code IS NOT NULL;

-- Комментарии
COMMENT ON COLUMN events.referral_code IS 'Реферальный код для этого события (например: EVENTBOT2024)';
COMMENT ON COLUMN events.referral_param IS 'Название параметра для реферального кода (по умолчанию: ref)';

