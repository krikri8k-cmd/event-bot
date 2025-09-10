BEGIN;

ALTER TABLE events
  ADD COLUMN IF NOT EXISTS city VARCHAR(128),
  ADD COLUMN IF NOT EXISTS country VARCHAR(64),
  ADD COLUMN IF NOT EXISTS organizer_id TEXT,
  ADD COLUMN IF NOT EXISTS organizer_url TEXT;

CREATE INDEX IF NOT EXISTS idx_events_city ON events (LOWER(city));
CREATE INDEX IF NOT EXISTS idx_events_country ON events (country);
CREATE INDEX IF NOT EXISTS idx_events_organizer_id ON events (organizer_id);

COMMIT;
