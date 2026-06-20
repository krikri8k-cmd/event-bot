-- Pre-check перед migrations/053_drop_task_templates.sql
-- Все блоки должны показывать безопасные значения перед применением миграции.

-- 1. Существует ли таблица
SELECT
    'task_templates_exists' AS check_name,
    EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'task_templates'
    ) AS value;

-- 2. Сколько строк в task_templates (ожидаем 0 или legacy-мусор)
SELECT
    'task_templates_rows' AS check_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'task_templates'
        ) THEN (SELECT COUNT(*)::bigint FROM task_templates)
        ELSE -1::bigint
    END AS value;

-- 3. user_tasks с template_id (ожидаем 0)
SELECT
    'user_tasks_with_template_id' AS check_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'user_tasks'
              AND column_name = 'template_id'
        ) THEN (SELECT COUNT(*)::bigint FROM user_tasks WHERE template_id IS NOT NULL)
        ELSE -1::bigint
    END AS value;

-- 4. daily_views_tasks с view_type = template (можно удалить)
SELECT
    'daily_views_template_rows' AS check_name,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'daily_views_tasks'
        ) THEN (
            SELECT COUNT(*)::bigint
            FROM daily_views_tasks
            WHERE view_type = 'template'
        )
        ELSE -1::bigint
    END AS value;

-- 5. FK на task_templates
SELECT
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type,
    kcu.column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
WHERE tc.table_schema = 'public'
  AND tc.constraint_type = 'FOREIGN KEY'
  AND tc.constraint_name ILIKE '%task_template%'
ORDER BY tc.table_name, tc.constraint_name;
