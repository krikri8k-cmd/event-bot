-- Миграция 004: Добавление поля is_active в таблицу moments
-- Исправляет ошибку: column "is_active" of relation "moments" does not exist

DO $$
BEGIN
    -- Проверяем существует ли поле is_active
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'moments' AND column_name = 'is_active'
    ) THEN
        -- Добавляем поле is_active с дефолтным значением TRUE
        ALTER TABLE moments ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;
        
        -- Убираем дефолт после добавления, чтобы он не прилипал к новым записям
        ALTER TABLE moments ALTER COLUMN is_active DROP DEFAULT;
        
        RAISE NOTICE 'Поле is_active добавлено в таблицу moments';
    ELSE
        RAISE NOTICE 'Поле is_active уже существует в таблице moments';
    END IF;
END $$;

-- Создаем индекс для производительности
CREATE INDEX IF NOT EXISTS idx_moments_is_active ON moments (is_active);

-- Обновляем существующие записи (если есть)
UPDATE moments SET is_active = TRUE WHERE is_active IS NULL;
