-- Добавление полей region и place_type в таблицу task_places
-- Для поддержки ротации локаций по регионам и типам мест

-- Добавляем поле региона
ALTER TABLE task_places 
ADD COLUMN IF NOT EXISTS region VARCHAR(50);
-- 'moscow', 'spb', 'bali', 'jakarta', etc.

-- Добавляем поле типа места
ALTER TABLE task_places 
ADD COLUMN IF NOT EXISTS place_type VARCHAR(50);
-- 'cafe', 'park', 'gym', 'yoga_studio', 'beach', 'temple', etc.

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_task_places_region ON task_places(region, category, place_type);
CREATE INDEX IF NOT EXISTS idx_task_places_coords ON task_places(lat, lng);

-- Комментарии к полям
COMMENT ON COLUMN task_places.region IS 'Регион места: moscow, spb, bali, jakarta, etc.';
COMMENT ON COLUMN task_places.place_type IS 'Тип места: cafe, park, gym, yoga_studio, beach, temple, etc.';

