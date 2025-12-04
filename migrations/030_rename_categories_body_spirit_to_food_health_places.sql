-- Переименование категорий: body/spirit → food/health/places
-- 
-- Распределение:
-- - body → health (спорт, йога, тренировки, медитация)
-- - spirit → places (храмы, музеи, выставки, прогулки, парки)
-- - Новые задания для food будут созданы отдельно

-- 1. Обновляем категории в таблице tasks
UPDATE tasks
SET category = 'health'
WHERE category = 'body';

UPDATE tasks
SET category = 'places'
WHERE category = 'spirit';

-- 2. Обновляем категории в таблице task_places
UPDATE task_places
SET category = 'health'
WHERE category = 'body';

UPDATE task_places
SET category = 'places'
WHERE category = 'spirit';

-- 3. Обновляем комментарии к полю category (если есть)
COMMENT ON COLUMN tasks.category IS 'Категория задания: food (еда), health (здоровье), places (интересные места)';
COMMENT ON COLUMN task_places.category IS 'Категория места: food (еда), health (здоровье), places (интересные места)';


