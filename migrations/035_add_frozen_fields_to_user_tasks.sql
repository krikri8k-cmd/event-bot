-- Добавление полей для хранения "замороженных" GPT-данных в user_tasks
-- Это гарантирует, что задание всегда показывает то же описание, которое видел пользователь при принятии

ALTER TABLE user_tasks
ADD COLUMN IF NOT EXISTS frozen_title VARCHAR(255),
ADD COLUMN IF NOT EXISTS frozen_description TEXT,
ADD COLUMN IF NOT EXISTS frozen_task_hint VARCHAR(200),
ADD COLUMN IF NOT EXISTS frozen_category VARCHAR(20);

COMMENT ON COLUMN user_tasks.frozen_title IS 'Зафиксированное название задания (из GPT или task_places.task_hint)';
COMMENT ON COLUMN user_tasks.frozen_description IS 'Зафиксированное описание задания (из GPT или шаблона)';
COMMENT ON COLUMN user_tasks.frozen_task_hint IS 'Зафиксированная подсказка задания (из task_places.task_hint)';
COMMENT ON COLUMN user_tasks.frozen_category IS 'Зафиксированная категория задания';

-- Индекс для поиска заданий с замороженными данными
CREATE INDEX IF NOT EXISTS idx_user_tasks_frozen_data 
ON user_tasks(user_id, status) 
WHERE frozen_title IS NOT NULL;

