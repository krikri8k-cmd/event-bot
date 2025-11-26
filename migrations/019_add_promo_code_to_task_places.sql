-- Добавляем поле promo_code в таблицу task_places
ALTER TABLE task_places
ADD COLUMN IF NOT EXISTS promo_code VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_task_places_promo_code ON task_places(promo_code) WHERE promo_code IS NOT NULL;

COMMENT ON COLUMN task_places.promo_code IS 'Промокод или реферальный код для партнерских локаций';

