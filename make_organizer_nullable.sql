-- Делаем organizer_id nullable для тестовых событий
ALTER TABLE events ALTER COLUMN organizer_id DROP NOT NULL;
