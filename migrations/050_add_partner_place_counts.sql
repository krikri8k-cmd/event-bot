-- Денормализованные счётчики мест у партнёра (соответствуют ORM-модели Partner).
-- Раньше эти значения отдавало представление partner_stats, которое убрали в 048.
-- Теперь это реальные колонки таблицы partners. Идемпотентно: безопасно применять повторно.

ALTER TABLE partners
ADD COLUMN IF NOT EXISTS linked_places_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE partners
ADD COLUMN IF NOT EXISTS active_places_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE partners
ADD COLUMN IF NOT EXISTS places_with_promo_count INTEGER NOT NULL DEFAULT 0;
