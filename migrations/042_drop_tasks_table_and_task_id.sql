-- ТЗ: Удаление legacy таблицы tasks и колонки user_tasks.task_id
-- Запускать после обновления кода (код больше не использует Task/task_id).

-- 1. Удалить записи user_tasks, ссылающиеся на tasks (если остались)
DELETE FROM user_tasks WHERE task_id IS NOT NULL;

-- 2. Удалить FK и колонку task_id (PostgreSQL)
ALTER TABLE user_tasks DROP CONSTRAINT IF EXISTS user_tasks_task_id_fkey;
ALTER TABLE user_tasks DROP COLUMN IF EXISTS task_id;

-- 3. Удалить таблицу tasks
DROP TABLE IF EXISTS tasks;
