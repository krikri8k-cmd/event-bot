-- Добавление поля task_hint (короткое задание/подсказка) в таблицу task_places

ALTER TABLE task_places
ADD COLUMN IF NOT EXISTS task_hint VARCHAR(200);

COMMENT ON COLUMN task_places.task_hint IS 'Короткое задание/подсказка для места (1 предложение). Например: "Попробуй кофе, поговори с бариста"';

-- Индекс для поиска мест без подсказок (для будущей AI генерации)
CREATE INDEX IF NOT EXISTS idx_task_places_task_hint_null ON task_places(category, place_type) WHERE task_hint IS NULL;


