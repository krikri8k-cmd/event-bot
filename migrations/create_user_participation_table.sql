-- Создание таблицы для участия пользователей в событиях
-- Включает автоочистку старых событий

CREATE TABLE IF NOT EXISTS user_participation (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    participation_type VARCHAR(20) NOT NULL CHECK (participation_type IN ('going', 'maybe')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Уникальность: пользователь может иметь только один статус для события
    UNIQUE(user_id, event_id)
);

-- Индексы для производительности
CREATE INDEX IF NOT EXISTS idx_user_participation_user_id ON user_participation(user_id);
CREATE INDEX IF NOT EXISTS idx_user_participation_event_id ON user_participation(event_id);
CREATE INDEX IF NOT EXISTS idx_user_participation_type ON user_participation(participation_type);
CREATE INDEX IF NOT EXISTS idx_user_participation_created_at ON user_participation(created_at);

-- Составной индекс для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_user_participation_user_type ON user_participation(user_id, participation_type);

-- Функция для автоочистки старых событий
CREATE OR REPLACE FUNCTION cleanup_expired_participations()
RETURNS TEXT AS $$
DECLARE
    deleted_count INTEGER;
    result_text TEXT;
BEGIN
    -- Удаляем участия для событий, которые закончились более суток назад
    DELETE FROM user_participation 
    WHERE event_id IN (
        SELECT id FROM events 
        WHERE starts_at < NOW() - INTERVAL '1 day'
    );
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    result_text := format('Удалено %s записей участия для завершившихся событий', deleted_count);
    
    RETURN result_text;
END;
$$ LANGUAGE plpgsql;

-- Создаем задачу для автоматической очистки (если используется pg_cron)
-- Можно запускать ежедневно в 3:00
-- SELECT cron.schedule('cleanup-expired-participations', '0 3 * * *', 'SELECT cleanup_expired_participations();');

-- Комментарии к таблице
COMMENT ON TABLE user_participation IS 'Участие пользователей в событиях (пойду/возможно)';
COMMENT ON COLUMN user_participation.user_id IS 'ID пользователя Telegram';
COMMENT ON COLUMN user_participation.event_id IS 'ID события из таблицы events';
COMMENT ON COLUMN user_participation.participation_type IS 'Тип участия: going (пойду) или maybe (возможно)';
COMMENT ON COLUMN user_participation.created_at IS 'Когда пользователь добавил событие';

-- Функция для получения событий пользователя по типу участия
CREATE OR REPLACE FUNCTION get_user_participations(
    p_user_id BIGINT,
    p_participation_type VARCHAR(20) DEFAULT NULL
)
RETURNS TABLE (
    event_id INTEGER,
    event_title VARCHAR,
    event_starts_at TIMESTAMP WITH TIME ZONE,
    event_location_name VARCHAR,
    event_city VARCHAR,
    participation_type VARCHAR(20),
    created_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        e.id,
        e.title,
        e.starts_at,
        e.location_name,
        e.city,
        up.participation_type,
        up.created_at
    FROM user_participation up
    JOIN events e ON up.event_id = e.id
    WHERE up.user_id = p_user_id
    AND (p_participation_type IS NULL OR up.participation_type = p_participation_type)
    AND e.starts_at > NOW() -- Только будущие события
    ORDER BY e.starts_at ASC;
END;
$$ LANGUAGE plpgsql;
