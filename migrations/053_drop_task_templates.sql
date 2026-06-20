-- Удаление legacy таблицы task_templates (шаблоны заданий «Цель на районе»).
-- Запускать после обновления кода: квесты создаются из task_places через tasks_service.py.

-- 1. Очистить daily_views_tasks, ссылающиеся на шаблоны
DELETE FROM daily_views_tasks WHERE view_type = 'template';

-- 2. Удалить FK и колонку template_id из user_tasks (если остались от старой схемы)
ALTER TABLE user_tasks DROP CONSTRAINT IF EXISTS user_tasks_template_id_fkey;
ALTER TABLE user_tasks DROP COLUMN IF EXISTS template_id;

-- 3. Удалить индекс и таблицу
DROP INDEX IF EXISTS idx_task_templates_category;
DROP TABLE IF EXISTS task_templates;
