-- Добавление таблиц для функции "Цель на Районе"

-- 1. Места для заданий
CREATE TABLE IF NOT EXISTS task_places (
    id SERIAL PRIMARY KEY,
    category VARCHAR(20) NOT NULL, -- 'body', 'spirit', 'career', 'social'
    name VARCHAR(255) NOT NULL,
    description TEXT,
    lat FLOAT NOT NULL,
    lng FLOAT NOT NULL,
    google_maps_url TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at_utc TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Шаблоны заданий
CREATE TABLE IF NOT EXISTS task_templates (
    id SERIAL PRIMARY KEY,
    category VARCHAR(20) NOT NULL, -- 'body', 'spirit', 'career', 'social'
    place_type VARCHAR(50) NOT NULL, -- 'park', 'cafe', 'library', etc.
    title VARCHAR(120) NOT NULL,
    description TEXT NOT NULL,
    rocket_value INTEGER DEFAULT 1,
    created_at_utc TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Пользовательские задания (экземпляры)
CREATE TABLE IF NOT EXISTS user_tasks (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    template_id INTEGER REFERENCES task_templates(id),
    category VARCHAR(20) NOT NULL,
    title VARCHAR(120) NOT NULL,
    description TEXT NOT NULL,
    rocket_value INTEGER DEFAULT 1,
    
    -- Место выполнения
    place_id VARCHAR(100), -- Google Places ID
    place_name VARCHAR(255),
    place_lat FLOAT,
    place_lng FLOAT,
    place_url TEXT, -- Google Maps ссылка
    
    -- Статус и время
    status VARCHAR(20) DEFAULT 'active', -- 'active', 'done', 'cancelled'
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Заметка пользователя
    user_note TEXT,
    
    created_at_utc TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Дневной журнал просмотров (для избежания повторов)
CREATE TABLE IF NOT EXISTS daily_views (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    view_type VARCHAR(20) NOT NULL, -- 'template', 'place'
    view_key VARCHAR(100) NOT NULL, -- template_id или place_id
    view_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at_utc TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, view_type, view_key, view_date)
);

-- Индексы для производительности
CREATE INDEX IF NOT EXISTS idx_task_places_category ON task_places(category);
CREATE INDEX IF NOT EXISTS idx_task_places_coords ON task_places(lat, lng);
CREATE INDEX IF NOT EXISTS idx_task_templates_category ON task_templates(category);
CREATE INDEX IF NOT EXISTS idx_user_tasks_user_status ON user_tasks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_user_tasks_started_at ON user_tasks(started_at);
CREATE INDEX IF NOT EXISTS idx_daily_views_user_date ON daily_views(user_id, view_date);

-- Добавляем поле rockets_balance в таблицу users
ALTER TABLE users ADD COLUMN IF NOT EXISTS rockets_balance INTEGER DEFAULT 0;
