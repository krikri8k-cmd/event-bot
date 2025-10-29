-- Исправление: удаляем новую таблицу и переименовываем старую
-- Сначала удаляем таблицу daily_views_tasks если она существует
DROP TABLE IF EXISTS daily_views_tasks;

-- Переименовываем существующую таблицу daily_views в daily_views_tasks
ALTER TABLE daily_views RENAME TO daily_views_tasks;

-- Добавляем комментарии к таблице и полям
COMMENT ON TABLE daily_views_tasks IS 'Отслеживание просмотренных заданий и мест пользователями для предотвращения повторений в системе квестов';

COMMENT ON COLUMN daily_views_tasks.user_id IS 'ID пользователя';
COMMENT ON COLUMN daily_views_tasks.view_type IS 'Тип просмотра: template (шаблон задания) или place (место)';
COMMENT ON COLUMN daily_views_tasks.view_key IS 'ID шаблона задания или места';
COMMENT ON COLUMN daily_views_tasks.view_date IS 'Дата и время просмотра';
