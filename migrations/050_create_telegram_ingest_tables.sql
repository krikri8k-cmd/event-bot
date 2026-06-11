-- Telegram event ingestion: source registry and diagnostic log

CREATE TABLE IF NOT EXISTS telegram_sources (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255) NULL,
    title VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    partner_id INTEGER REFERENCES partners(id) NULL,
    trust_level VARCHAR(50) NOT NULL DEFAULT 'moderated',
    default_categories JSONB DEFAULT '[]'::jsonb,
    default_city VARCHAR(100) DEFAULT 'bali',
    default_country VARCHAR(10) DEFAULT 'ID',
    timezone VARCHAR(100) DEFAULT 'Asia/Makassar',
    allow_default_coords BOOLEAN DEFAULT FALSE,
    default_lat DOUBLE PRECISION NULL,
    default_lng DOUBLE PRECISION NULL,
    default_contact VARCHAR(255) NULL,
    last_processed_message_id BIGINT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS telegram_ingest_log (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    stage VARCHAR(50) NOT NULL,
    reason VARCHAR(255) NOT NULL,
    raw_snippet TEXT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_telegram_ingest_log_created
    ON telegram_ingest_log(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_telegram_ingest_log_chat
    ON telegram_ingest_log(chat_id, created_at DESC);
