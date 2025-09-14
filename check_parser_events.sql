-- A. В БД есть два найденных парсером события?
SELECT id, title, starts_at, lat, lng
FROM events_parser
WHERE starts_at::date = (now() AT TIME ZONE 'Asia/Makassar')::date
ORDER BY starts_at;

-- B. Они попадают в выдачу «рядом» (15 км, твоя точка)?
WITH window AS (
  SELECT (date_trunc('day', (now() AT TIME ZONE 'Asia/Makassar')) AT TIME ZONE 'UTC') AS s,
         (date_trunc('day', (now() AT TIME ZONE 'Asia/Makassar')) AT TIME ZONE 'UTC') + interval '1 day' - interval '1 second' AS e
)
SELECT id, title, lat, lng
FROM events_parser, window
WHERE starts_at BETWEEN window.s AND window.e
  AND (
    lat IS NULL OR lng IS NULL OR
    (lat IS NOT NULL AND lng IS NOT NULL AND 
     earth_distance(ll_to_earth(-8.675326, 115.230191), ll_to_earth(lat, lng)) <= 15000)
  );

-- C. Проверяем события пользователей
SELECT id, title, starts_at, lat, lng
FROM events_user
WHERE starts_at::date = (now() AT TIME ZONE 'Asia/Makassar')::date
ORDER BY starts_at;
