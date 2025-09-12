-- =====================================================
-- МИГРАЦИЯ: Добавление управления статусами событий
-- =====================================================
-- 
-- Цель: Доработать таблицу events для поддержки статусов
-- open, closed, canceled и автомодерации
--
-- Безопасность: Все изменения обратимые
-- =====================================================

BEGIN;

-- 1. Обновляем существующие записи без статуса
UPDATE events 
SET status = 'open' 
WHERE status IS NULL OR status = '';

-- 2. Добавляем ограничение NOT NULL для organizer_id
-- (если есть записи без organizer_id, их нужно будет обработать отдельно)
ALTER TABLE events 
ALTER COLUMN organizer_id SET NOT NULL;

-- 3. Добавляем ограничение NOT NULL для starts_at
-- (если есть записи без starts_at, их нужно будет обработать отдельно)
ALTER TABLE events 
ALTER COLUMN starts_at SET NOT NULL;

-- 4. Устанавливаем default значение для status
ALTER TABLE events 
ALTER COLUMN status SET DEFAULT 'open';

-- 5. Добавляем CHECK ограничение для валидных статусов
ALTER TABLE events 
ADD CONSTRAINT events_status_check 
CHECK (status IN ('open', 'closed', 'canceled', 'active', 'draft'));

-- 6. Создаем индекс для быстрого поиска по статусу и дате
CREATE INDEX IF NOT EXISTS idx_events_status_starts_at 
ON events (status, starts_at);

-- 7. Создаем индекс для поиска событий организатора
CREATE INDEX IF NOT EXISTS idx_events_organizer_status 
ON events (organizer_id, status);

-- 8. Обновляем существующие статусы 'active' в 'open' (если нужно)
UPDATE events 
SET status = 'open' 
WHERE status = 'active';

COMMIT;

-- =====================================================
-- ПРОВЕРКА МИГРАЦИИ
-- =====================================================

-- Проверяем, что все ограничения применились
SELECT 
    column_name, 
    is_nullable, 
    column_default,
    data_type
FROM information_schema.columns 
WHERE table_name = 'events' 
  AND column_name IN ('organizer_id', 'starts_at', 'status')
ORDER BY column_name;

-- Проверяем текущие статусы
SELECT status, COUNT(*) as count
FROM events 
GROUP BY status 
ORDER BY status;

-- Проверяем ограничения
SELECT conname, contype, pg_get_constraintdef(oid)
FROM pg_constraint 
WHERE conrelid = 'events'::regclass
  AND conname LIKE '%status%';

-- =====================================================
-- ФУНКЦИЯ АВТОМОДЕРАЦИИ
-- =====================================================

-- Создаем функцию для автоматического закрытия событий
CREATE OR REPLACE FUNCTION auto_close_events()
RETURNS INTEGER AS $$
DECLARE
    closed_count INTEGER;
BEGIN
    UPDATE events
    SET status = 'closed', 
        updated_at_utc = NOW()
    WHERE status = 'open'
      AND starts_at::date < CURRENT_DATE;
    
    GET DIAGNOSTICS closed_count = ROW_COUNT;
    
    RETURN closed_count;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- ТЕСТИРОВАНИЕ
-- =====================================================

-- Тестируем функцию автомодерации (безопасно)
SELECT auto_close_events() as events_closed;

-- Проверяем результат
SELECT 
    status, 
    COUNT(*) as count,
    MIN(starts_at) as earliest,
    MAX(starts_at) as latest
FROM events 
GROUP BY status 
ORDER BY status;
