-- Разделение счетчика событий на World и Community версии
-- events_created_total -> events_created_world + events_created_community

-- Удаляем старый счетчик
ALTER TABLE users DROP COLUMN IF EXISTS events_created_total;

-- Добавляем новые счетчики
ALTER TABLE users ADD COLUMN IF NOT EXISTS events_created_world INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS events_created_community INTEGER DEFAULT 0;

-- Добавляем комментарии
COMMENT ON COLUMN users.events_created_world IS 'Количество событий созданных в версии World (личные чаты)';
COMMENT ON COLUMN users.events_created_community IS 'Количество событий созданных в версии Community (групповые чаты)';

-- Заполняем данные из существующих событий
-- World версия - события из таблицы events с source='user'
UPDATE users 
SET events_created_world = (
    SELECT COUNT(*) 
    FROM events 
    WHERE organizer_id = users.id AND source = 'user'
);

-- Community версия - события из таблицы events_community
UPDATE users 
SET events_created_community = (
    SELECT COUNT(*) 
    FROM events_community 
    WHERE organizer_id = users.id
);

-- Создаем индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_users_events_created_world ON users(events_created_world);
CREATE INDEX IF NOT EXISTS idx_users_events_created_community ON users(events_created_community);

