-- Миграция для исправления лимитов колонок и дублирования событий
-- Выполнить: python apply_sql.py fix_column_limits.sql

-- 1. Увеличиваем лимиты колонок в events_parser
ALTER TABLE events_parser ALTER COLUMN title TYPE VARCHAR(255);
ALTER TABLE events_parser ALTER COLUMN description TYPE TEXT;

-- 2. Увеличиваем лимиты колонок в events  
ALTER TABLE events ALTER COLUMN title TYPE VARCHAR(255);
ALTER TABLE events ALTER COLUMN description TYPE TEXT;

-- 3. Проверяем индексы для ON CONFLICT
CREATE UNIQUE INDEX IF NOT EXISTS unique_source_external_id_events_parser 
ON events_parser (source, external_id);

CREATE UNIQUE INDEX IF NOT EXISTS unique_source_external_id_events 
ON events (source, external_id);

-- 4. Очищаем дублированные записи (если есть)
-- Удаляем дубли, оставляя только самые новые
DELETE FROM events_parser a USING events_parser b 
WHERE a.id < b.id AND a.source = b.source AND a.external_id = b.external_id;

DELETE FROM events a USING events b 
WHERE a.id < b.id AND a.source = b.source AND a.external_id = b.external_id;
