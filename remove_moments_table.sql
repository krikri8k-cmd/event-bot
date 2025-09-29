-- Удаление таблицы moments - функция Moments полностью удалена
-- Выполнить в Railway PostgreSQL базе данных

-- Проверяем, существует ли таблица moments
DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'moments') THEN
        -- Удаляем таблицу moments
        DROP TABLE moments CASCADE;
        RAISE NOTICE 'Таблица moments успешно удалена';
    ELSE
        RAISE NOTICE 'Таблица moments не существует';
    END IF;
END $$;
