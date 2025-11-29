-- Добавление поля task_type для разделения заданий на городские (urban) и островные (island)

-- 1. Добавляем task_type в таблицу tasks
ALTER TABLE tasks 
ADD COLUMN IF NOT EXISTS task_type VARCHAR(20) DEFAULT 'urban';

-- Комментарий к полю
COMMENT ON COLUMN tasks.task_type IS 'Тип задания: urban (городские) или island (островные)';

-- Индекс для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_tasks_category_task_type ON tasks(category, task_type, order_index);

-- 2. Добавляем task_type в таблицу task_places
ALTER TABLE task_places 
ADD COLUMN IF NOT EXISTS task_type VARCHAR(20) DEFAULT 'urban';

-- Комментарий к полю
COMMENT ON COLUMN task_places.task_type IS 'Тип задания, для которого подходит это место: urban (городские) или island (островные)';

-- Индекс для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_task_places_category_task_type ON task_places(category, task_type, region, place_type);

-- 3. Обновляем существующие данные
-- По умолчанию все существующие задания и места будут urban
-- Потом можно будет вручную обновить островные задания и места

