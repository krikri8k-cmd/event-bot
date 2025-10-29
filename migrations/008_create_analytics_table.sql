-- Создание таблицы analytics для отслеживания метрик бота
-- Гибкая структура с JSONB для различных типов метрик

CREATE TABLE IF NOT EXISTS analytics (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(50) NOT NULL,  -- Тип метрики: 'user_activity', 'group_stats', 'daily_active'
    metric_value JSONB NOT NULL,       -- Гибкие данные в JSON формате
    date DATE NOT NULL,                -- Дата метрики
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Индексы для быстрого поиска
    CONSTRAINT unique_metric_date UNIQUE(metric_name, date)
);

-- Индексы для производительности
CREATE INDEX IF NOT EXISTS idx_analytics_metric_name ON analytics(metric_name);
CREATE INDEX IF NOT EXISTS idx_analytics_date ON analytics(date);
CREATE INDEX IF NOT EXISTS idx_analytics_metric_date ON analytics(metric_name, date);

-- GIN индекс для быстрого поиска по JSONB
CREATE INDEX IF NOT EXISTS idx_analytics_metric_value ON analytics USING GIN(metric_value);

-- Комментарии к таблице
COMMENT ON TABLE analytics IS 'Аналитика и метрики бота - гибкая структура для отслеживания активности';
COMMENT ON COLUMN analytics.metric_name IS 'Тип метрики: user_activity, group_stats, daily_active, group_activity';
COMMENT ON COLUMN analytics.metric_value IS 'Данные метрики в JSON формате';
COMMENT ON COLUMN analytics.date IS 'Дата метрики';
COMMENT ON COLUMN analytics.created_at IS 'Время создания записи';

-- Функция для получения метрик за период
CREATE OR REPLACE FUNCTION get_analytics_metrics(
    p_metric_name VARCHAR(50),
    p_start_date DATE DEFAULT NULL,
    p_end_date DATE DEFAULT NULL
)
RETURNS TABLE (
    date DATE,
    metric_value JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.date,
        a.metric_value
    FROM analytics a
    WHERE a.metric_name = p_metric_name
    AND (p_start_date IS NULL OR a.date >= p_start_date)
    AND (p_end_date IS NULL OR a.date <= p_end_date)
    ORDER BY a.date DESC;
END;
$$ LANGUAGE plpgsql;

-- Функция для получения последней метрики
CREATE OR REPLACE FUNCTION get_latest_metric(p_metric_name VARCHAR(50))
RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT metric_value INTO result
    FROM analytics
    WHERE metric_name = p_metric_name
    ORDER BY date DESC
    LIMIT 1;
    
    RETURN COALESCE(result, '{}'::jsonb);
END;
$$ LANGUAGE plpgsql;

