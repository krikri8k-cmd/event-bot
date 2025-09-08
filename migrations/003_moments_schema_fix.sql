-- Миграция 003: Исправление схемы moments
-- Добавляет недостающие поля и исправляет структуру таблицы

-- Создаем таблицу moments если её нет
CREATE TABLE IF NOT EXISTS moments (
  id               BIGSERIAL PRIMARY KEY,
  user_id          BIGINT        NOT NULL,
  creator_username TEXT,
  text             TEXT          NOT NULL,
  lat              DOUBLE PRECISION NOT NULL,
  lon              DOUBLE PRECISION NOT NULL,
  created_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
  expires_at       TIMESTAMPTZ   NOT NULL,
  is_active        BOOLEAN       NOT NULL DEFAULT TRUE,
  radius_km        INTEGER       NOT NULL DEFAULT 20,
  duration_min     INTEGER       NOT NULL,
  CHECK (duration_min IN (30, 60, 120)),
  CHECK (radius_km BETWEEN 1 AND 50)
);

-- Если таблица уже существует, добавляем недостающие колонки
DO $$ 
BEGIN
  -- Добавляем колонки если их нет
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS creator_username TEXT; 
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
  
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;     
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
  
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS is_active BOOLEAN;          
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
  
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS radius_km INTEGER;          
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
  
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS duration_min INTEGER;       
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
  
  -- Добавляем новые поля для совместимости с кодом
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS username TEXT; 
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
  
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS title TEXT; 
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
  
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS location_lat DOUBLE PRECISION; 
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
  
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS location_lng DOUBLE PRECISION; 
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
  
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ; 
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
  
  -- Legacy поля для совместимости
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS template TEXT; 
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
  
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION; 
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
  
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION; 
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
  
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS created_utc TIMESTAMPTZ; 
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
  
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS expires_utc TIMESTAMPTZ; 
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
  
  BEGIN 
    ALTER TABLE moments ADD COLUMN IF NOT EXISTS status TEXT; 
  EXCEPTION WHEN duplicate_column THEN 
    -- Колонка уже существует, ничего не делаем
  END;
END $$;

-- Заполняем дефолты для новых полей (одноразово и безопасно)
UPDATE moments
SET
  is_active    = COALESCE(is_active, TRUE),
  radius_km    = COALESCE(radius_km, 20),
  duration_min = COALESCE(duration_min, 60),
  expires_at   = COALESCE(expires_at, created_at + (COALESCE(duration_min, 60) || ' minutes')::interval)
WHERE is_active IS NULL OR radius_km IS NULL OR duration_min IS NULL OR expires_at IS NULL;

-- Синхронизируем legacy поля с новыми (только если поля существуют)
DO $$
BEGIN
  -- Проверяем существование полей перед обновлением
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'moments' AND column_name = 'username') THEN
    UPDATE moments
    SET
      username = COALESCE(username, creator_username),
      title = COALESCE(title, text),
      location_lat = COALESCE(location_lat, lat),
      location_lng = COALESCE(location_lng, lng),
      created_at = COALESCE(created_at, created_utc),
      expires_at = COALESCE(expires_at, expires_utc)
    WHERE username IS NULL OR title IS NULL OR location_lat IS NULL OR location_lng IS NULL OR created_at IS NULL OR expires_at IS NULL;
  END IF;
END $$;

-- Создаем индексы для производительности
CREATE INDEX IF NOT EXISTS idx_moments_active_exp ON moments (is_active, expires_at);
CREATE INDEX IF NOT EXISTS idx_moments_user_created ON moments (user_id, created_at DESC);

-- Создаем индексы для геолокации только если поля существуют
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'moments' AND column_name = 'lat') THEN
    CREATE INDEX IF NOT EXISTS idx_moments_geo ON moments (lat, lng);
  END IF;
  
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'moments' AND column_name = 'location_lat') THEN
    CREATE INDEX IF NOT EXISTS idx_moments_location_geo ON moments (location_lat, location_lng);
  END IF;
END $$;

-- Добавляем ограничения если их нет
DO $$
BEGIN
  -- Проверяем и добавляем CHECK constraints
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.check_constraints 
    WHERE constraint_name = 'moments_duration_check'
  ) THEN
    ALTER TABLE moments ADD CONSTRAINT moments_duration_check 
    CHECK (duration_min IN (30, 60, 120));
  END IF;
  
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.check_constraints 
    WHERE constraint_name = 'moments_radius_check'
  ) THEN
    ALTER TABLE moments ADD CONSTRAINT moments_radius_check 
    CHECK (radius_km BETWEEN 1 AND 50);
  END IF;
END $$;
