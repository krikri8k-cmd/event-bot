-- БЕЗОПАСНЫЙ cleanup: удаление старых таблиц после миграции
-- Включает проверки целостности, резервные копии и откат

-- Создаем функцию для безопасного удаления таблиц
CREATE OR REPLACE FUNCTION safe_drop_events_tables() 
RETURNS TEXT AS $$
DECLARE
    result_text TEXT := '';
    events_count INTEGER;
    parser_count INTEGER;
    user_count INTEGER;
    parser_migrated INTEGER;
    user_migrated INTEGER;
    backup_exists BOOLEAN;
BEGIN
    -- 1. Проверяем текущее состояние
    SELECT COUNT(*) INTO events_count FROM events;
    SELECT COUNT(*) INTO parser_count FROM events_parser;
    SELECT COUNT(*) INTO user_count FROM events_user;
    SELECT COUNT(*) INTO parser_migrated FROM events WHERE source != 'user' AND source IS NOT NULL;
    SELECT COUNT(*) INTO user_migrated FROM events WHERE source = 'user';
    
    result_text := result_text || format('Состояние до cleanup: events=%s, parser=%s, user=%s', 
                                        events_count, parser_count, user_count) || E'\n';
    result_text := result_text || format('Мигрировано: parser=%s, user=%s', 
                                        parser_migrated, user_migrated) || E'\n';
    
    -- 2. Проверяем что миграция была успешной
    IF parser_count > 0 AND parser_migrated = 0 THEN
        RETURN result_text || 'ОШИБКА: События parser не мигрированы!' || E'\n';
    END IF;
    
    IF user_count > 0 AND user_migrated = 0 THEN
        RETURN result_text || 'ОШИБКА: События user не мигрированы!' || E'\n';
    END IF;
    
    -- 3. Проверяем существование резервных копий
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_name = 'events_parser_backup'
    ) INTO backup_exists;
    
    IF NOT backup_exists THEN
        -- Создаем резервные копии
        EXECUTE 'CREATE TABLE events_parser_backup AS SELECT * FROM events_parser';
        result_text := result_text || 'Создана резервная копия events_parser_backup' || E'\n';
    END IF;
    
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_name = 'events_user_backup'
    ) INTO backup_exists;
    
    IF NOT backup_exists THEN
        -- Создаем резервные копии
        EXECUTE 'CREATE TABLE events_user_backup AS SELECT * FROM events_user';
        result_text := result_text || 'Создана резервная копия events_user_backup' || E'\n';
    END IF;
    
    -- 4. Проверяем что все данные корректно мигрированы
    -- Проверка 1: Количество записей
    IF parser_count != parser_migrated THEN
        RETURN result_text || format('ОШИБКА: Не все parser события мигрированы! %s != %s', 
                                    parser_count, parser_migrated) || E'\n';
    END IF;
    
    IF user_count != user_migrated THEN
        RETURN result_text || format('ОШИБКА: Не все user события мигрированы! %s != %s', 
                                    user_count, user_migrated) || E'\n';
    END IF;
    
    -- Проверка 2: Сравнение данных (выборочно)
    -- Проверяем первые 100 записей из каждой таблицы
    IF NOT EXISTS (
        SELECT 1 FROM (
            SELECT source, external_id, title, starts_at
            FROM events_parser 
            ORDER BY id 
            LIMIT 100
        ) p
        WHERE NOT EXISTS (
            SELECT 1 FROM events e 
            WHERE e.source = p.source 
            AND e.external_id = p.external_id
            AND e.title = p.title
        )
    ) THEN
        result_text := result_text || 'Проверка parser данных: OK' || E'\n';
    ELSE
        RETURN result_text || 'ОШИБКА: Несоответствие данных parser!' || E'\n';
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM (
            SELECT organizer_id, title, starts_at
            FROM events_user 
            ORDER BY id 
            LIMIT 100
        ) u
        WHERE NOT EXISTS (
            SELECT 1 FROM events e 
            WHERE e.source = 'user'
            AND e.organizer_id = u.organizer_id
            AND e.title = u.title
            AND e.starts_at = u.starts_at
        )
    ) THEN
        result_text := result_text || 'Проверка user данных: OK' || E'\n';
    ELSE
        RETURN result_text || 'ОШИБКА: Несоответствие данных user!' || E'\n';
    END IF;
    
    -- 5. Все проверки пройдены - можно удалять
    result_text := result_text || 'Все проверки пройдены успешно' || E'\n';
    
    -- 6. Удаляем таблицы
    BEGIN
        DROP TABLE IF EXISTS events_user CASCADE;
        result_text := result_text || 'Удалена таблица events_user' || E'\n';
        
        DROP TABLE IF EXISTS events_parser CASCADE;
        result_text := result_text || 'Удалена таблица events_parser' || E'\n';
        
        -- Обновляем статистику
        ANALYZE events;
        result_text := result_text || 'Обновлена статистика таблицы events' || E'\n';
        
    EXCEPTION WHEN OTHERS THEN
        result_text := result_text || 'ОШИБКА при удалении таблиц: ' || SQLERRM || E'\n';
        RETURN result_text;
    END;
    
    result_text := result_text || 'Cleanup завершен успешно!' || E'\n';
    RETURN result_text;
    
END;
$$ LANGUAGE plpgsql;

-- Выполняем безопасный cleanup
SELECT safe_drop_events_tables();

-- Удаляем функцию
DROP FUNCTION IF EXISTS safe_drop_events_tables();

-- Финальная проверка
SELECT 
    'Cleanup завершен!' as status,
    (SELECT COUNT(*) FROM events WHERE source != 'user' AND source IS NOT NULL) as parser_events_in_events,
    (SELECT COUNT(*) FROM events WHERE source = 'user') as user_events_in_events,
    (SELECT COUNT(*) FROM events) as total_events,
    (SELECT COUNT(*) FROM events_parser_backup) as parser_backup_count,
    (SELECT COUNT(*) FROM events_user_backup) as user_backup_count;
