-- Исправление ограничений в таблице analytics
-- Добавляем правильный уникальный индекс для ON CONFLICT

-- Удаляем старое ограничение если есть
ALTER TABLE analytics DROP CONSTRAINT IF EXISTS unique_metric_date;

-- Добавляем новое составное ограничение
ALTER TABLE analytics 
ADD CONSTRAINT unique_metric_scope_target_date 
UNIQUE (metric_name, scope, COALESCE(target_id, 0), date);

-- Исправляем функцию для получения активных пользователей в группе
-- (используем приблизительную оценку через bot_messages)
CREATE OR REPLACE FUNCTION get_group_active_users(p_group_id BIGINT, p_days INTEGER DEFAULT 7)
RETURNS INTEGER AS $$
DECLARE
    active_count INTEGER;
BEGIN
    -- Подсчитываем уникальные сообщения в группе как приблизительную оценку активности
    SELECT COUNT(DISTINCT message_id) INTO active_count
    FROM bot_messages 
    WHERE chat_id = p_group_id
    AND created_at >= NOW() - (p_days || ' days')::INTERVAL;
    
    RETURN COALESCE(active_count, 0);
END;
$$ LANGUAGE plpgsql;

-- Обновляем комментарии
COMMENT ON CONSTRAINT unique_metric_scope_target_date ON analytics IS 'Уникальность по метрике, области, цели и дате';

