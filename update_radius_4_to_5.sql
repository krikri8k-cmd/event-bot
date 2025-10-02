-- Миграция: обновить всех пользователей с радиусом 4 км на 5 км
-- Это исправляет проблему, когда пользователи имеют старый радиус 4 км

UPDATE users 
SET default_radius_km = 5 
WHERE default_radius_km = 4;

-- Показать результат
SELECT 
    COUNT(*) as updated_users,
    'Users with radius 4km updated to 5km' as description
FROM users 
WHERE default_radius_km = 5;
