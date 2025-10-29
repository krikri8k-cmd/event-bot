-- Переименование таблицы daily_views в daily_views_tasks для большей ясности
-- Эта таблица используется для отслеживания просмотренных заданий в системе квестов

-- Переименовываем таблицу
ALTER TABLE daily_views RENAME TO daily_views_tasks;

-- Обновляем комментарий к таблице
COMMENT ON TABLE daily_views_tasks IS 'Отслеживание просмотренных заданий и мест пользователями для предотвращения повторений в системе квестов';

-- Обновляем комментарии к полям
COMMENT ON COLUMN daily_views_tasks.user_id IS 'ID пользователя';
COMMENT ON COLUMN daily_views_tasks.view_type IS 'Тип просмотра: template (шаблон задания) или place (место)';
COMMENT ON COLUMN daily_views_tasks.view_key IS 'ID шаблона задания или места';
COMMENT ON COLUMN daily_views_tasks.view_date IS 'Дата и время просмотра';
