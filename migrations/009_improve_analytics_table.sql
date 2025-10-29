-- Улучшение таблицы analytics для унифицированной структуры метрик
-- Добавляем поля scope и target_id для более гибкой организации данных

-- Добавляем новые поля
ALTER TABLE analytics 
ADD COLUMN IF NOT EXISTS scope VARCHAR(50) DEFAULT 'global',
ADD COLUMN IF NOT EXISTS target_id BIGINT;

-- Обновляем существующие записи (если есть)
UPDATE analytics 
SET scope = 'global' 
WHERE scope IS NULL;

-- Создаем новые индексы для производительности
CREATE INDEX IF NOT EXISTS idx_analytics_scope ON analytics(scope);
CREATE INDEX IF NOT EXISTS idx_analytics_target_id ON analytics(target_id);
CREATE INDEX IF NOT EXISTS idx_analytics_metric_scope ON analytics(metric_name, scope);
CREATE INDEX IF NOT EXISTS idx_analytics_scope_target ON analytics(scope, target_id);
CREATE INDEX IF NOT EXISTS idx_analytics_date_metric ON analytics(date, metric_name);

-- Комментарии к новым полям
COMMENT ON COLUMN analytics.scope IS 'Область метрики: global, group, user, event';
COMMENT ON COLUMN analytics.target_id IS 'ID группы, пользователя или события (если scope != global)';

-- Функция для получения DAU за период
CREATE OR REPLACE FUNCTION get_dau_trend(
    p_start_date DATE DEFAULT NULL,
    p_end_date DATE DEFAULT NULL
)
RETURNS TABLE (
    date DATE,
    total_users INTEGER,
    new_users INTEGER,
    returning_users INTEGER,
    private_chats INTEGER,
    group_chats INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.date,
        (a.metric_value->>'total_users')::INTEGER as total_users,
        (a.metric_value->>'new_users')::INTEGER as new_users,
        (a.metric_value->>'returning_users')::INTEGER as returning_users,
        (a.metric_value->>'private_chats')::INTEGER as private_chats,
        (a.metric_value->>'group_chats')::INTEGER as group_chats
    FROM analytics a
    WHERE a.metric_name = 'daily_user_activity'
    AND a.scope = 'global'
    AND (p_start_date IS NULL OR a.date >= p_start_date)
    AND (p_end_date IS NULL OR a.date <= p_end_date)
    ORDER BY a.date DESC;
END;
$$ LANGUAGE plpgsql;

-- Функция для получения топ активных групп
CREATE OR REPLACE FUNCTION get_top_active_groups(
    p_date DATE DEFAULT CURRENT_DATE,
    p_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    target_id BIGINT,
    group_name TEXT,
    active_users INTEGER,
    events_created INTEGER,
    commands_used INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.target_id,
        a.metric_value->>'group_name' as group_name,
        (a.metric_value->>'active_users')::INTEGER as active_users,
        (a.metric_value->>'events_created')::INTEGER as events_created,
        (a.metric_value->>'commands_used')::INTEGER as commands_used
    FROM analytics a
    WHERE a.metric_name = 'group_activity'
    AND a.scope = 'group'
    AND a.date = p_date
    ORDER BY (a.metric_value->>'active_users')::INTEGER DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- Функция для получения общей статистики групп
CREATE OR REPLACE FUNCTION get_group_statistics(
    p_date DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    total_groups INTEGER,
    active_groups INTEGER,
    total_members INTEGER,
    active_members INTEGER,
    groups_with_events INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        (a.metric_value->>'total_groups')::INTEGER as total_groups,
        (a.metric_value->>'active_groups')::INTEGER as active_groups,
        (a.metric_value->>'total_members')::INTEGER as total_members,
        (a.metric_value->>'active_members')::INTEGER as active_members,
        (a.metric_value->>'groups_with_events')::INTEGER as groups_with_events
    FROM analytics a
    WHERE a.metric_name = 'group_statistics'
    AND a.scope = 'global'
    AND a.date = p_date
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- Функция для получения метрик по группе за период
CREATE OR REPLACE FUNCTION get_group_metrics(
    p_group_id BIGINT,
    p_start_date DATE DEFAULT NULL,
    p_end_date DATE DEFAULT NULL
)
RETURNS TABLE (
    date DATE,
    group_name TEXT,
    active_users INTEGER,
    events_created INTEGER,
    commands_used INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.date,
        a.metric_value->>'group_name' as group_name,
        (a.metric_value->>'active_users')::INTEGER as active_users,
        (a.metric_value->>'events_created')::INTEGER as events_created,
        (a.metric_value->>'commands_used')::INTEGER as commands_used
    FROM analytics a
    WHERE a.metric_name = 'group_activity'
    AND a.scope = 'group'
    AND a.target_id = p_group_id
    AND (p_start_date IS NULL OR a.date >= p_start_date)
    AND (p_end_date IS NULL OR a.date <= p_end_date)
    ORDER BY a.date DESC;
END;
$$ LANGUAGE plpgsql;

-- Функция для получения последних метрик
CREATE OR REPLACE FUNCTION get_latest_metrics()
RETURNS TABLE (
    metric_name VARCHAR(50),
    scope VARCHAR(50),
    target_id BIGINT,
    metric_value JSONB,
    date DATE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.metric_name,
        a.scope,
        a.target_id,
        a.metric_value,
        a.date
    FROM analytics a
    INNER JOIN (
        SELECT 
            metric_name, 
            scope, 
            COALESCE(target_id, 0) as target_id,
            MAX(date) as max_date
        FROM analytics 
        GROUP BY metric_name, scope, COALESCE(target_id, 0)
    ) latest ON a.metric_name = latest.metric_name 
    AND a.scope = latest.scope 
    AND COALESCE(a.target_id, 0) = latest.target_id
    AND a.date = latest.max_date
    ORDER BY a.metric_name, a.scope, a.target_id;
END;
$$ LANGUAGE plpgsql;

