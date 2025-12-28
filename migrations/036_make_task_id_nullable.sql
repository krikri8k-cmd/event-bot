-- Делаем task_id nullable в user_tasks
-- Это позволяет создавать задания из GPT без привязки к шаблону

ALTER TABLE user_tasks
ALTER COLUMN task_id DROP NOT NULL;

COMMENT ON COLUMN user_tasks.task_id IS 'ID шаблона задания (nullable для GPT-генерированных заданий)';

