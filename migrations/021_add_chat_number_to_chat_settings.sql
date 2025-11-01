-- Migration: Добавление chat_number в chat_settings
-- Дата: 2025-11-01
-- Описание: Добавляет внутренний порядковый номер чата для отслеживания количества чатов

-- Создаем последовательность для chat_number
CREATE SEQUENCE IF NOT EXISTS chat_number_seq;

-- Добавляем колонку chat_number в таблицу chat_settings
ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS chat_number INTEGER UNIQUE;

-- Создаем индекс для быстрого доступа
CREATE INDEX IF NOT EXISTS idx_chat_settings_chat_number ON chat_settings(chat_number) WHERE chat_number IS NOT NULL;

-- Комментарии к колонке
COMMENT ON COLUMN chat_settings.chat_number IS 'Внутренний порядковый номер чата (1, 2, 3...) для отслеживания количества чатов';

