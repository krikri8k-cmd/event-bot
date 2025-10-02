-- Просмотр ракет всех пользователей
SELECT 
    id,
    username,
    full_name,
    rockets_balance,
    created_at_utc
FROM users 
WHERE rockets_balance > 0
ORDER BY rockets_balance DESC;

-- Просмотр всех пользователей с ракетами (включая 0)
SELECT 
    id,
    username,
    full_name,
    rockets_balance,
    created_at_utc
FROM users 
ORDER BY rockets_balance DESC, created_at_utc DESC;

-- Статистика по ракетам
SELECT 
    COUNT(*) as total_users,
    SUM(rockets_balance) as total_rockets,
    AVG(rockets_balance) as avg_rockets,
    MAX(rockets_balance) as max_rockets
FROM users;
