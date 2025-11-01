-- Migration: Добавление информации об админах в chat_settings
-- Дата: 2025-11-01
-- Описание: Добавляет поля для хранения списка админов и их количества

-- Добавляем колонку admin_ids для хранения JSON массива ID админов
ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS admin_ids TEXT;

-- Добавляем колонку admin_count для хранения количества админов
ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS admin_count INTEGER;

-- Комментарии к колонкам
COMMENT ON COLUMN chat_settings.admin_ids IS 'JSON массив ID всех администраторов группы';
COMMENT ON COLUMN chat_settings.admin_count IS 'Количество админов в группе';

