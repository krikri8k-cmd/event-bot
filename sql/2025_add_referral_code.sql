-- 2025_add_referral_code.sql
-- Добавляет поддержку реферальных кодов для источников событий

-- Добавляем колонку referral_code в event_sources
ALTER TABLE event_sources ADD COLUMN IF NOT EXISTS referral_code TEXT;
ALTER TABLE event_sources ADD COLUMN IF NOT EXISTS referral_param TEXT DEFAULT 'ref';

-- Комментарии для документации
COMMENT ON COLUMN event_sources.referral_code IS 'Реферальный код для добавления к URL событий (например: PARTNER2024)';
COMMENT ON COLUMN event_sources.referral_param IS 'Название параметра для реферального кода (по умолчанию: ref)';

