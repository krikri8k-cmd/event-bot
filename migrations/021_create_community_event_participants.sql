-- Создание таблицы для участников Community событий
-- Отдельная таблица для изолированных Community событий

CREATE TABLE IF NOT EXISTS community_event_participants (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL,
    user_id BIGINT NOT NULL,
    username VARCHAR(255), -- Сохраняем username для быстрого отображения
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Связь с событием
    CONSTRAINT fk_community_participant_event 
        FOREIGN KEY (event_id) REFERENCES events_community(id) ON DELETE CASCADE,
    
    -- Уникальность: один пользователь может быть участником события только один раз
    UNIQUE(event_id, user_id)
);

-- Индексы для производительности
CREATE INDEX IF NOT EXISTS idx_community_participants_event_id ON community_event_participants(event_id);
CREATE INDEX IF NOT EXISTS idx_community_participants_user_id ON community_event_participants(user_id);
CREATE INDEX IF NOT EXISTS idx_community_participants_created_at ON community_event_participants(created_at);

-- Комментарии
COMMENT ON TABLE community_event_participants IS 'Участники событий в групповых чатах (Community)';
COMMENT ON COLUMN community_event_participants.event_id IS 'ID события из events_community';
COMMENT ON COLUMN community_event_participants.user_id IS 'ID пользователя Telegram';
COMMENT ON COLUMN community_event_participants.username IS 'Username пользователя для отображения';

