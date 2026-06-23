-- Несколько подкатегорий на место (как теги у событий).
-- place_type остаётся основным типом; place_tags — доп. slug через JSON-массив.

ALTER TABLE task_places
ADD COLUMN IF NOT EXISTS place_tags JSONB NOT NULL DEFAULT '[]'::jsonb;
