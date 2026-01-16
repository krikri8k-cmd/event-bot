-- Миграция 037: Добавление поля community_name в таблицу events
-- Безопасная миграция - добавляет поле только если его нет

DO $$
BEGIN
    -- Добавляем community_name если его нет
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'events' AND column_name = 'community_name'
    ) THEN
        ALTER TABLE events ADD COLUMN community_name VARCHAR(120);
        RAISE NOTICE 'Добавлено поле community_name в таблицу events';
    ELSE
        RAISE NOTICE 'Поле community_name уже существует в таблице events';
    END IF;
END $$;
