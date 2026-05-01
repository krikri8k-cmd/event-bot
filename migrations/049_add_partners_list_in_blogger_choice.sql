-- Платная витрина «Выбор блогера»: только партнёры с list_in_blogger_choice попадают в кнопку.
-- Места по-прежнему могут иметь partner_id + review_url в категориях еда/здоровье/места.

ALTER TABLE partners
ADD COLUMN IF NOT EXISTS list_in_blogger_choice BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN partners.list_in_blogger_choice IS
    'If true, partner is listed in Telegram «Выбор блогера»; linking places does not imply this flag.';

-- Сохраняем текущее поведение: все активные партнёры остаются в кнопке до ручного снятия флага.
UPDATE partners
SET list_in_blogger_choice = TRUE
WHERE is_active IS TRUE;
