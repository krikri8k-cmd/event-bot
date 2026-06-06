-- Этап №2: партнёры (блогеры) + ссылки на видео-обзоры мест

-- 1) Таблица партнёров
CREATE TABLE IF NOT EXISTS partners (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(50) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    main_url VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at_utc TIMESTAMPTZ DEFAULT NOW(),
    updated_at_utc TIMESTAMPTZ DEFAULT NOW()
);

-- Уникальность slug без учета регистра
CREATE UNIQUE INDEX IF NOT EXISTS uq_partners_slug_lower ON partners ((LOWER(slug)));

-- 2) Поля в task_places
ALTER TABLE task_places
ADD COLUMN IF NOT EXISTS partner_id INTEGER REFERENCES partners(id) ON DELETE SET NULL;

ALTER TABLE task_places
ADD COLUMN IF NOT EXISTS review_url VARCHAR(255);

CREATE INDEX IF NOT EXISTS idx_task_places_partner_id ON task_places(partner_id);
