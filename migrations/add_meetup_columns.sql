-- Миграция для добавления колонок и индексов для Meetup интеграции
-- Выполнить в psql: \i migrations/add_meetup_columns.sql

-- Добавляем новые колонки
ALTER TABLE events
  ADD COLUMN IF NOT EXISTS source TEXT,
  ADD COLUMN IF NOT EXISTS external_id TEXT,
  ADD COLUMN IF NOT EXISTS url TEXT,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

-- Создаём индексы для производительности
CREATE INDEX IF NOT EXISTS idx_events_coords ON events (lat, lng);
CREATE INDEX IF NOT EXISTS idx_events_starts_at ON events (starts_at);
CREATE INDEX IF NOT EXISTS idx_events_source_external_id ON events (source, external_id);

-- Уникальный индекс для дедупликации
CREATE UNIQUE INDEX IF NOT EXISTS ux_events_source_ext
  ON events (source, external_id)
  WHERE external_id IS NOT NULL;

-- Проверяем результат
SELECT 
  column_name, 
  data_type, 
  is_nullable
FROM information_schema.columns 
WHERE table_name = 'events' 
ORDER BY ordinal_position;

-- Показываем индексы
SELECT 
  indexname, 
  indexdef 
FROM pg_indexes 
WHERE tablename = 'events';
