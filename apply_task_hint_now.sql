-- ============================================
-- ПРИМЕНИТЕ ЭТОТ SQL В ВЕБ-ИНТЕРФЕЙСЕ БАЗЫ ДАННЫХ
-- ============================================
-- Просто скопируйте весь этот файл и выполните в SQL редакторе
-- ============================================

-- Шаг 1: Добавляем столбец task_hint
ALTER TABLE task_places
ADD COLUMN IF NOT EXISTS task_hint VARCHAR(200);

-- Шаг 2: Добавляем комментарий
COMMENT ON COLUMN task_places.task_hint IS 'Короткое задание/подсказка для места (1 предложение). Например: "Попробуй кофе, поговори с бариста"';

-- Шаг 3: Создаем индекс для быстрого поиска мест без подсказок
CREATE INDEX IF NOT EXISTS idx_task_places_task_hint_null 
ON task_places(category, place_type) 
WHERE task_hint IS NULL;

-- ============================================
-- ПРОВЕРКА: Выполните этот запрос, чтобы убедиться, что столбец создан
-- ============================================
SELECT 
    column_name, 
    data_type, 
    character_maximum_length,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'task_places' 
  AND column_name = 'task_hint';

-- Если запрос вернул результат - столбец создан успешно! ✅



