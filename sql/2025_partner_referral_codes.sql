-- 2025_partner_referral_codes.sql
-- Простая таблица для хранения реферальных кодов партнёров
-- Связывает URL источника с реферальным кодом

CREATE TABLE IF NOT EXISTS partner_referral_codes (
    id BIGSERIAL PRIMARY KEY,
    source_url TEXT NOT NULL,           -- URL источника (ICS календарь, API и т.д.)
    referral_code TEXT NOT NULL,         -- Реферальный код (например: 'EVENTBOT2024')
    referral_param TEXT DEFAULT 'ref',   -- Название параметра ('ref', 'affiliate' и т.д.)
    partner_name TEXT,                   -- Название партнёра (для удобства)
    is_active BOOLEAN DEFAULT TRUE,      -- Включен/выключен
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Уникальный индекс по URL источника
CREATE UNIQUE INDEX IF NOT EXISTS ux_partner_referral_source_url 
    ON partner_referral_codes (lower(source_url));

-- Индекс для быстрого поиска активных
CREATE INDEX IF NOT EXISTS ix_partner_referral_active 
    ON partner_referral_codes (is_active) 
    WHERE is_active = TRUE;

-- Комментарии
COMMENT ON TABLE partner_referral_codes IS 'Реферальные коды для партнёрских источников событий';
COMMENT ON COLUMN partner_referral_codes.source_url IS 'URL источника (ICS календарь, API endpoint)';
COMMENT ON COLUMN partner_referral_codes.referral_code IS 'Реферальный код для добавления к URL событий';
COMMENT ON COLUMN partner_referral_codes.referral_param IS 'Название параметра в URL (по умолчанию: ref)';

