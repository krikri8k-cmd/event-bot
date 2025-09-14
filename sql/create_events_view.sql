-- Создание VIEW для объединенных событий по регионам

-- Для Бали
CREATE OR REPLACE VIEW events_all_bali AS
SELECT 
    'user' AS source_type, 
    id, 
    title, 
    description,
    starts_at, 
    ends_at, 
    lat, 
    lng, 
    url, 
    location_name,
    location_url,
    country,
    city,
    created_at_utc,
    organizer_id
FROM events_user
WHERE country = 'ID' AND city = 'bali'

UNION ALL

SELECT 
    'parser' AS source_type, 
    id, 
    title, 
    description,
    starts_at, 
    ends_at, 
    lat, 
    lng, 
    url, 
    location_name,
    location_url,
    country,
    city,
    created_at_utc,
    NULL as organizer_id
FROM events_parser
WHERE country = 'ID' AND city = 'bali';

-- Для Москвы
CREATE OR REPLACE VIEW events_all_msk AS
SELECT 
    'user' AS source_type, 
    id, 
    title, 
    description,
    starts_at, 
    ends_at, 
    lat, 
    lng, 
    url, 
    location_name,
    location_url,
    country,
    city,
    created_at_utc,
    organizer_id
FROM events_user
WHERE country = 'RU' AND city = 'moscow'

UNION ALL

SELECT 
    'parser' AS source_type, 
    id, 
    title, 
    description,
    starts_at, 
    ends_at, 
    lat, 
    lng, 
    url, 
    location_name,
    location_url,
    country,
    city,
    created_at_utc,
    NULL as organizer_id
FROM events_parser
WHERE country = 'RU' AND city = 'moscow';

-- Для СПб
CREATE OR REPLACE VIEW events_all_spb AS
SELECT 
    'user' AS source_type, 
    id, 
    title, 
    description,
    starts_at, 
    ends_at, 
    lat, 
    lng, 
    url, 
    location_name,
    location_url,
    country,
    city,
    created_at_utc,
    organizer_id
FROM events_user
WHERE country = 'RU' AND city = 'spb'

UNION ALL

SELECT 
    'parser' AS source_type, 
    id, 
    title, 
    description,
    starts_at, 
    ends_at, 
    lat, 
    lng, 
    url, 
    location_name,
    location_url,
    country,
    city,
    created_at_utc,
    NULL as organizer_id
FROM events_parser
WHERE country = 'RU' AND city = 'spb';

-- Индексы для производительности
CREATE INDEX IF NOT EXISTS idx_events_user_bali ON events_user (country, city, starts_at);
CREATE INDEX IF NOT EXISTS idx_events_parser_bali ON events_parser (country, city, starts_at);
CREATE INDEX IF NOT EXISTS idx_events_user_msk ON events_user (country, city, starts_at);
CREATE INDEX IF NOT EXISTS idx_events_parser_msk ON events_parser (country, city, starts_at);
CREATE INDEX IF NOT EXISTS idx_events_user_spb ON events_user (country, city, starts_at);
CREATE INDEX IF NOT EXISTS idx_events_parser_spb ON events_parser (country, city, starts_at);
