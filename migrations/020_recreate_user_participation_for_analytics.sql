-- Migration: Пересоздание таблицы user_participation для аналитики взаимодействий
-- Дата: 2025-10-31
-- Описание: Полностью переделывает таблицу для отслеживания всех взаимодействий пользователей с событиями

-- ⚠️ ВНИМАНИЕ: Эта миграция удаляет старую таблицу и все данные!
-- Если нужны данные о участии (going/maybe), их нужно экспортировать заранее

-- Удаляем старую таблицу и связанные объекты
DROP TABLE IF EXISTS user_participation CASCADE;
DROP FUNCTION IF EXISTS cleanup_expired_participations() CASCADE;
DROP FUNCTION IF EXISTS get_user_participations(BIGINT, VARCHAR) CASCADE;

-- Создаем новую таблицу для аналитики взаимодействий
CREATE TABLE user_participation (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    event_id INTEGER NOT NULL,
    group_chat_id BIGINT, -- NULL для World, значение для Community
    list_view BOOLEAN DEFAULT FALSE, -- Показано ли событие в списке "Что рядом"
    click_source BOOLEAN DEFAULT FALSE, -- Нажал ли на источник/автора
    click_route BOOLEAN DEFAULT FALSE, -- Нажал ли на маршрут
    participation_type VARCHAR(50), -- Заготовка для будущего функционала участия (пока NULL, потом going/maybe и т.д.)
    
    -- Связи с внешними таблицами
    CONSTRAINT fk_user_participation_event 
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
    
    -- Уникальность: одна запись на user_id + event_id (обновляем при повторных взаимодействиях)
    UNIQUE(user_id, event_id)
);

-- Индексы для производительности
CREATE INDEX idx_user_participation_user_id ON user_participation(user_id);
CREATE INDEX idx_user_participation_event_id ON user_participation(event_id);
CREATE INDEX idx_user_participation_group_chat_id ON user_participation(group_chat_id) WHERE group_chat_id IS NOT NULL;
CREATE INDEX idx_user_participation_created_at ON user_participation(created_at);
CREATE INDEX idx_user_participation_user_event ON user_participation(user_id, event_id);
CREATE INDEX idx_user_participation_part_type ON user_participation(participation_type) WHERE participation_type IS NOT NULL;

-- Комментарии к таблице и колонкам
COMMENT ON TABLE user_participation IS 'Аналитика взаимодействий пользователей с событиями';
COMMENT ON COLUMN user_participation.user_id IS 'ID пользователя Telegram';
COMMENT ON COLUMN user_participation.created_at IS 'Дата и время первого взаимодействия с событием';
COMMENT ON COLUMN user_participation.updated_at IS 'Дата и время последнего обновления записи';
COMMENT ON COLUMN user_participation.event_id IS 'ID события из таблицы events';
COMMENT ON COLUMN user_participation.group_chat_id IS 'ID группового чата (для Community). NULL если событие из World';
COMMENT ON COLUMN user_participation.list_view IS 'Показано ли событие в списке при поиске "Что рядом"';
COMMENT ON COLUMN user_participation.click_source IS 'Нажал ли пользователь на источник или автора события';
COMMENT ON COLUMN user_participation.click_route IS 'Нажал ли пользователь на кнопку маршрута';
COMMENT ON COLUMN user_participation.participation_type IS 'Заготовка для будущего функционала участия (пока NULL, потом going/maybe и т.д.)';

