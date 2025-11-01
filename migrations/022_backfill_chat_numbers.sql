-- Migration: Бекфилл chat_number для существующих чатов
-- Дата: 2025-11-01
-- Описание: Назначает chat_number для всех существующих записей в chat_settings

-- Сначала сбрасываем последовательность на 1
SELECT setval('chat_number_seq', 1, false);

-- Назначаем chat_number всем чатам, у которых его еще нет
-- Создаем временную функцию для назначения номеров
DO $$
DECLARE
    rec RECORD;
    next_num INTEGER;
BEGIN
    next_num := 1;
    
    -- Проходим по всем чатам в порядке создания
    FOR rec IN 
        SELECT chat_id 
        FROM chat_settings 
        WHERE chat_number IS NULL 
        ORDER BY created_at, chat_id
    LOOP
        UPDATE chat_settings 
        SET chat_number = next_num 
        WHERE chat_id = rec.chat_id;
        
        next_num := next_num + 1;
    END LOOP;
    
    -- Устанавливаем sequence на правильное значение после бекфилла
    PERFORM setval('chat_number_seq', COALESCE((SELECT MAX(chat_number) FROM chat_settings), 0) + 1, false);
END $$;

