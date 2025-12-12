-- Миграция 23: Удаление таблицы community_event_participants
-- Эта таблица больше не нужна, так как участники теперь хранятся
-- в столбцах participants_count и participants_ids таблицы events_community

-- Удаляем таблицу (CASCADE удалит все связанные индексы и ограничения)
DROP TABLE IF EXISTS community_event_participants CASCADE;

