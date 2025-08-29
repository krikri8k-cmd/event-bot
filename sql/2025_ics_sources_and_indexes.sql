-- 2025_ics_sources_and_indexes.sql
-- Безопасный скрипт: создаёт таблицу event_sources (для ICS/интеграций)
-- и добивает полезные индексы/колонки, если их ещё нет.

-- 1) Таблица источников событий (ICS, API и т.д.)
CREATE TABLE IF NOT EXISTS event_sources (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'ics',           -- 'ics' | 'api' | ...
  url  TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  fetch_interval_minutes INTEGER NOT NULL DEFAULT 60,
  last_fetched_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_event_sources_url
  ON event_sources (lower(url));

-- 2) Дополняем таблицу events, если она есть
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
     WHERE table_schema = 'public' AND table_name = 'events'
  ) THEN
    -- Базовые поля для дедупликации/ссылок на первоисточник
    ALTER TABLE events ADD COLUMN IF NOT EXISTS source      TEXT;
    ALTER TABLE events ADD COLUMN IF NOT EXISTS external_id TEXT;
    ALTER TABLE events ADD COLUMN IF NOT EXISTS url         TEXT;

    -- Гео/время (если вдруг нет)
    ALTER TABLE events ADD COLUMN IF NOT EXISTS lat        DOUBLE PRECISION;
    ALTER TABLE events ADD COLUMN IF NOT EXISTS lng        DOUBLE PRECISION;
    ALTER TABLE events ADD COLUMN IF NOT EXISTS starts_at  TIMESTAMPTZ;
    ALTER TABLE events ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
  END IF;
END $$;

-- 3) Индексы для скорости
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.tables
     WHERE table_schema = 'public' AND table_name = 'events'
  ) THEN
    CREATE INDEX IF NOT EXISTS ix_events_starts_at ON events (starts_at);
    CREATE INDEX IF NOT EXISTS ix_events_source_ext ON events (source, external_id);
  END IF;
END $$;
