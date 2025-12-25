-- Добавление полей для хранения информации о конкретном месте в user_tasks
-- Это позволяет сохранять информацию о месте, которое пользователь добавил,
-- чтобы она не менялась при добавлении других мест другими пользователями

-- Добавляем поля для хранения информации о месте
ALTER TABLE user_tasks
ADD COLUMN IF NOT EXISTS place_id INTEGER REFERENCES task_places(id),
ADD COLUMN IF NOT EXISTS place_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS place_url TEXT,
ADD COLUMN IF NOT EXISTS promo_code VARCHAR(100);

-- Индекс для быстрого поиска по place_id
CREATE INDEX IF NOT EXISTS idx_user_tasks_place_id ON user_tasks(place_id);

