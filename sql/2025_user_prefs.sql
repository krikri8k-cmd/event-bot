-- Миграция для хранения настроек пользователей
-- Идемпотентная миграция

CREATE TABLE IF NOT EXISTS user_prefs (
  telegram_user_id BIGINT PRIMARY KEY,
  lat DOUBLE PRECISION,
  lon DOUBLE PRECISION,
  radius_km DOUBLE PRECISION DEFAULT 10,
  city TEXT,
  country TEXT,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Создаем индекс если его нет
CREATE INDEX IF NOT EXISTS idx_user_prefs_updated_at ON user_prefs(updated_at);

-- Добавляем индекс для событий если его нет
CREATE INDEX IF NOT EXISTS idx_events_lat_lon ON events(lat, lon);
