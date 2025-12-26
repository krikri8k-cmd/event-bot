-- Диагностический запрос: проверка place_id в заданиях
-- Запустить в БД для проверки проблемы

-- 1. Проверяем, есть ли place_id в user_tasks
SELECT 
    ut.id,
    ut.place_id,
    ut.place_name,
    ut.place_url,
    tp.id as task_place_id,
    tp.name as task_place_name,
    tp.google_maps_url as task_place_url
FROM user_tasks ut
LEFT JOIN task_places tp ON ut.place_id = tp.id
WHERE ut.status = 'active'
ORDER BY ut.accepted_at DESC
LIMIT 10;

-- 2. Проверяем, есть ли Google place_id в task_places (если поле существует)
-- Если поля нет - нужно добавить миграцию
SELECT 
    id,
    name,
    google_maps_url,
    -- Если есть поле google_place_id, раскомментировать:
    -- google_place_id
FROM task_places
WHERE is_active = true
LIMIT 10;

-- 3. Проверяем формат URL в task_places
-- Если URL содержит только координаты (q=lat,lng) - проблема здесь
SELECT 
    id,
    name,
    google_maps_url,
    CASE 
        WHEN google_maps_url LIKE '%place_id%' THEN '✅ Есть place_id'
        WHEN google_maps_url LIKE '%q=%' THEN '❌ Только координаты'
        WHEN google_maps_url LIKE '%/place/%' THEN '✅ Есть /place/'
        ELSE '❓ Неизвестный формат'
    END as url_type
FROM task_places
WHERE is_active = true
LIMIT 20;

