-- Расширение partners + аналитические представления

-- 1) Новые поля в partners (без дублирования данных мест)
ALTER TABLE partners
ADD COLUMN IF NOT EXISTS telegram_contact VARCHAR(100);

ALTER TABLE partners
ADD COLUMN IF NOT EXISTS default_promo_code VARCHAR(100);

ALTER TABLE partners
ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 0;

ALTER TABLE partners
ADD COLUMN IF NOT EXISTS is_featured BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE partners
ADD COLUMN IF NOT EXISTS notes TEXT;

-- 2) Представление со статистикой по партнёрам
CREATE OR REPLACE VIEW partner_stats AS
SELECT
    p.id AS partner_id,
    p.slug,
    p.display_name,
    p.main_url,
    p.telegram_contact,
    p.default_promo_code,
    p.priority,
    p.is_featured,
    p.is_active,
    COUNT(tp.id) AS places_count,
    COUNT(tp.id) FILTER (WHERE tp.is_active IS TRUE) AS active_places_count,
    COUNT(tp.id) FILTER (
        WHERE tp.promo_code IS NOT NULL
          AND BTRIM(tp.promo_code) <> ''
    ) AS places_with_promo_count
FROM partners p
LEFT JOIN task_places tp ON tp.partner_id = p.id
GROUP BY
    p.id,
    p.slug,
    p.display_name,
    p.main_url,
    p.telegram_contact,
    p.default_promo_code,
    p.priority,
    p.is_featured,
    p.is_active;

-- 3) Представление "какое место за кем закреплено"
CREATE OR REPLACE VIEW task_places_with_partner AS
SELECT
    tp.id AS place_id,
    tp.name,
    tp.name_en,
    tp.category,
    tp.region,
    tp.task_type,
    tp.is_active,
    tp.promo_code,
    tp.review_url,
    tp.google_maps_url,
    tp.partner_id,
    p.slug AS partner_slug,
    p.display_name AS partner_name,
    p.main_url AS partner_main_url,
    p.telegram_contact AS partner_telegram_contact,
    p.default_promo_code AS partner_default_promo_code,
    p.priority AS partner_priority,
    p.is_featured AS partner_is_featured,
    p.is_active AS partner_is_active
FROM task_places tp
LEFT JOIN partners p ON p.id = tp.partner_id;
