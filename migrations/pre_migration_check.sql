-- Проверка перед миграцией: анализ данных и потенциальных конфликтов

-- 1. Общая статистика таблиц
SELECT 
    'events' as table_name,
    COUNT(*) as record_count,
    COUNT(DISTINCT source) as unique_sources
FROM events
UNION ALL
SELECT 
    'events_parser' as table_name,
    COUNT(*) as record_count,
    COUNT(DISTINCT source) as unique_sources
FROM events_parser
UNION ALL
SELECT 
    'events_user' as table_name,
    COUNT(*) as record_count,
    COUNT(DISTINCT source) as unique_sources
FROM events_user;

-- 2. Анализ источников в events_parser
SELECT 
    source,
    COUNT(*) as count,
    MIN(created_at_utc) as earliest,
    MAX(created_at_utc) as latest
FROM events_parser
GROUP BY source
ORDER BY count DESC;

-- 3. Анализ пользовательских событий
SELECT 
    COUNT(*) as total_user_events,
    COUNT(DISTINCT organizer_id) as unique_organizers,
    COUNT(DISTINCT city) as unique_cities,
    MIN(created_at_utc) as earliest,
    MAX(created_at_utc) as latest
FROM events_user;

-- 4. Проверка на потенциальные дубликаты
-- Между events и events_parser
SELECT 
    'events vs events_parser' as conflict_type,
    COUNT(*) as potential_conflicts
FROM events e
JOIN events_parser ep ON e.external_id = ep.external_id 
    AND e.source = ep.source
WHERE e.source IS NOT NULL;

-- Между events и events_user
SELECT 
    'events vs events_user' as conflict_type,
    COUNT(*) as potential_conflicts
FROM events e
JOIN events_user eu ON e.organizer_id = eu.organizer_id
    AND e.title = eu.title
    AND e.starts_at = eu.starts_at
WHERE e.source = 'user';

-- 5. Проверка структуры полей
-- Поля которые есть в events_parser но нет в events
SELECT 
    'events_parser fields not in events' as check_type,
    CASE 
        WHEN NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='events' AND column_name='country') 
        THEN 'country - MISSING'
        ELSE 'country - OK'
    END as country_status,
    CASE 
        WHEN NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='events' AND column_name='city') 
        THEN 'city - MISSING'
        ELSE 'city - OK'
    END as city_status,
    CASE 
        WHEN NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='events' AND column_name='venue_name') 
        THEN 'venue_name - MISSING'
        ELSE 'venue_name - OK'
    END as venue_name_status,
    CASE 
        WHEN NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='events' AND column_name='address') 
        THEN 'address - MISSING'
        ELSE 'address - OK'
    END as address_status;

-- 6. Проверка индексов
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes 
WHERE tablename IN ('events', 'events_parser', 'events_user')
ORDER BY tablename, indexname;

-- 7. Проверка ограничений (constraints)
SELECT 
    tc.table_name,
    tc.constraint_name,
    tc.constraint_type,
    kcu.column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu 
    ON tc.constraint_name = kcu.constraint_name
WHERE tc.table_name IN ('events', 'events_parser', 'events_user')
ORDER BY tc.table_name, tc.constraint_type;

-- 8. Рекомендации
SELECT 
    'Рекомендации' as section,
    CASE 
        WHEN (SELECT COUNT(*) FROM events_parser) = 0 
        THEN '✅ events_parser пуста - миграция безопасна'
        ELSE '⚠️ events_parser содержит данные - проверьте дубликаты'
    END as parser_recommendation,
    CASE 
        WHEN (SELECT COUNT(*) FROM events_user) = 0 
        THEN '✅ events_user пуста - миграция безопасна'
        ELSE '⚠️ events_user содержит данные - проверьте дубликаты'
    END as user_recommendation,
    CASE 
        WHEN (SELECT COUNT(*) FROM events) = 0 
        THEN '✅ events пуста - миграция безопасна'
        ELSE '⚠️ events содержит данные - возможны конфликты'
    END as events_recommendation;
