-- Представление с удобным порядком колонок для пользователей
DROP VIEW IF EXISTS users_stats_view;
CREATE VIEW users_stats_view AS
SELECT
    u.id,
    u.username,
    u.full_name,
    u.rockets_balance,
    -- Сессии рядом и в нужном порядке
    u.total_sessions,
    u.total_sessions_world,
    u.total_sessions_community,
    -- Остальные метрики
    u.tasks_accepted_total,
    u.tasks_completed_total,
    u.events_created_world,
    u.events_created_community,
    (COALESCE(u.events_created_world,0) + COALESCE(u.events_created_community,0)) AS events_created_total,
    u.created_at_utc,
    u.updated_at_utc
FROM users u;


