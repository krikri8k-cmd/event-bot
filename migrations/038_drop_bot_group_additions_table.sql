-- Миграция 038: Удаление неиспользуемой таблицы bot_group_additions
-- Таблица не используется в коде, функционал перенесен в chat_settings
-- Безопасная миграция - удаляет таблицу только если она существует

DO $$
BEGIN
    -- Проверяем существование таблицы перед удалением
    IF EXISTS (
        SELECT 1 FROM information_schema.tables 
        WHERE table_name = 'bot_group_additions'
    ) THEN
        -- Удаляем таблицу
        DROP TABLE bot_group_additions;
        RAISE NOTICE 'Таблица bot_group_additions успешно удалена';
    ELSE
        RAISE NOTICE 'Таблица bot_group_additions не существует, пропускаем удаление';
    END IF;
END $$;
