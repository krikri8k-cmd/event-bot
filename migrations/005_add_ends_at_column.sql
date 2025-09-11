-- Добавляем колонку ends_at в таблицу events
-- Эта колонка нужна для хранения времени окончания события

ALTER TABLE events 
ADD COLUMN IF NOT EXISTS ends_at TIMESTAMPTZ;

-- Добавляем комментарий
COMMENT ON COLUMN events.ends_at IS 'Время окончания события (UTC)';
