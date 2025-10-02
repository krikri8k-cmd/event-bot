-- Обновить всех пользователей с радиусом 4 км на 5 км
UPDATE users 
SET default_radius_km = 5 
WHERE default_radius_km = 4;

-- Показать результат
SELECT 
    COUNT(*) as users_with_5km_radius,
    'Users updated from 4km to 5km radius' as description
FROM users 
WHERE default_radius_km = 5;
