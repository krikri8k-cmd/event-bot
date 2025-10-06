-- Создание таблицы events_community для событий в групповых чатах
-- Эта таблица полностью изолирована от основного функционала бота

CREATE TABLE IF NOT EXISTS events_community (
    id SERIAL PRIMARY KEY,
    group_id BIGINT NOT NULL,
    creator_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    date TIMESTAMP NOT NULL,
    description TEXT,
    city TEXT,
    location_name TEXT,
    created_at TIMESTAMP DEFAULT now()
);

-- Индексы для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_events_community_group_id ON events_community(group_id);
CREATE INDEX IF NOT EXISTS idx_events_community_date ON events_community(date);
CREATE INDEX IF NOT EXISTS idx_events_community_creator_id ON events_community(creator_id);

-- Комментарии для документации
COMMENT ON TABLE events_community IS 'События в групповых чатах (изолированно от основного бота)';
COMMENT ON COLUMN events_community.group_id IS 'ID группового чата';
COMMENT ON COLUMN events_community.creator_id IS 'ID создателя события';
COMMENT ON COLUMN events_community.date IS 'Дата и время события';
COMMENT ON COLUMN events_community.city IS 'Город события (вводится пользователем)';
COMMENT ON COLUMN events_community.location_name IS 'Название места или ссылка';
