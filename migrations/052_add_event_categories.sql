-- Категории событий для MyGuide (PR1: инфраструктура, без UI)
ALTER TABLE events
  ADD COLUMN IF NOT EXISTS categories JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS raw_category TEXT;
