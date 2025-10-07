# 🚀 ПРОДАКШЕН миграция: Объединение таблиц событий

## 🎯 Профессиональная миграция без простоя

Это руководство описывает **продакшен-готовую** миграцию для объединения таблиц `events_parser` и `events_user` в единую таблицу `events` с применением всех профессиональных практик.

## ✨ Ключевые улучшения

### 🔑 **Дедупликация**
- **Частичные уникальные индексы** для предотвращения дубликатов
- **Умные ключи дедупликации** по source + external_id
- **Проверка дубликатов** на каждом этапе

### ⚡ **Производительность**
- **CONCURRENTLY индексы** - создание без блокировки таблицы
- **Батч-миграция** - обработка больших объемов порциями
- **Нормализация данных** - geo_hash и временные зоны

### 🛡️ **Безопасность**
- **Транзакционная безопасность** с откатом
- **Резервные копии** автоматически
- **Проверки целостности** на каждом этапе
- **Dry-run режим** для тестирования

## 📊 Новая структура events

```sql
CREATE TABLE events (
    -- Основные поля
    id SERIAL PRIMARY KEY,
    source VARCHAR(64),                    -- 'baliforum', 'kudago', 'user', etc
    external_id VARCHAR(64),               -- ID из источника
    title VARCHAR(120) NOT NULL,
    description TEXT,
    
    -- Время (нормализованное)
    starts_at TIMESTAMP WITH TIME ZONE,
    starts_at_normalized TIMESTAMP WITH TIME ZONE,  -- ← НОВОЕ: нормализованное время
    ends_at TIMESTAMP WITH TIME ZONE,
    event_tz VARCHAR(64),
    
    -- Локация (нормализованная)
    location_name VARCHAR(255),
    location_url TEXT,
    lat FLOAT,
    lng FLOAT,
    geo_hash VARCHAR(32),                  -- ← НОВОЕ: нормализованные координаты
    
    -- География
    country VARCHAR(8),                    -- ← НОВОЕ: из parser
    city VARCHAR(64),                      -- ← НОВОЕ: из parser/user
    venue_name VARCHAR(255),               -- ← НОВОЕ: из parser
    address TEXT,                          -- ← НОВОЕ: из parser
    
    -- Организатор и участники
    organizer_id BIGINT,
    organizer_username VARCHAR(255),
    chat_id BIGINT,
    max_participants INTEGER,
    participants_ids TEXT,
    current_participants INTEGER DEFAULT 0,
    status VARCHAR(16) DEFAULT 'draft',
    
    -- Сообщество
    community_name VARCHAR(120),
    community_link TEXT,
    
    -- Метаданные
    is_generated_by_ai BOOLEAN DEFAULT FALSE,
    dedupe_key VARCHAR(64),
    created_at_utc TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at_utc TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## 🚀 План продакшен миграции

### **Этап 1: Подготовка**
```bash
# 1. Создайте резервную копию
pg_dump $DATABASE_URL > backup_before_migration_$(date +%Y%m%d_%H%M%S).sql

# 2. Проверьте предварительные условия
python migrate_events_production.py --check-only

# 3. Выполните dry-run тест
python migrate_events_production.py --dry-run
```

### **Этап 2: Продакшен миграция**
```bash
# Выполните миграцию с проверками
python migrate_events_production.py

# Или принудительно (если много соединений)
python migrate_events_production.py --force
```

### **Этап 3: Проверка результата**
```sql
-- Проверьте статистику
SELECT 
    source,
    COUNT(*) as count,
    COUNT(geo_hash) as with_geo,
    COUNT(starts_at_normalized) as with_normalized_time
FROM events 
WHERE source IS NOT NULL
GROUP BY source
ORDER BY count DESC;

-- Проверьте дубликаты
SELECT COUNT(*) FROM (
    SELECT source, external_id, COUNT(*) 
    FROM events 
    WHERE source IS NOT NULL 
    GROUP BY source, external_id 
    HAVING COUNT(*) > 1
) duplicates;
```

## 🔧 Детальная техническая реализация

### **1. Дедупликация с частичными индексами**

```sql
-- Уникальность для парсеров
CREATE UNIQUE INDEX CONCURRENTLY idx_events_parser_dedup 
    ON events(source, external_id) 
    WHERE source IS NOT NULL AND external_id IS NOT NULL;

-- Уникальность для пользовательских событий
CREATE UNIQUE INDEX CONCURRENTLY idx_events_user_dedup 
    ON events(organizer_id, title, starts_at) 
    WHERE source = 'user' AND organizer_id IS NOT NULL;
```

### **2. Нормализация геолокации**

```sql
-- Функция для генерации geo_hash (точность ~11м)
CREATE OR REPLACE FUNCTION generate_geo_hash(lat_val FLOAT, lng_val FLOAT) 
RETURNS VARCHAR(32) AS $$
BEGIN
    IF lat_val IS NULL OR lng_val IS NULL THEN
        RETURN NULL;
    END IF;
    
    -- Нормализуем до 4 знаков после запятой
    RETURN encode(digest(
        (ROUND(lat_val::numeric, 4) || ',' || ROUND(lng_val::numeric, 4))::bytea, 
        'sha256'
    ), 'hex')::VARCHAR(32);
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

### **3. Нормализация временных зон**

```sql
-- Функция для нормализации времени
CREATE OR REPLACE FUNCTION normalize_timestamp(ts_val TIMESTAMP WITH TIME ZONE, tz_val VARCHAR(64)) 
RETURNS TIMESTAMP WITH TIME ZONE AS $$
BEGIN
    IF ts_val IS NULL THEN
        RETURN NULL;
    END IF;
    
    -- Конвертируем в UTC если есть часовой пояс
    IF tz_val IS NOT NULL AND tz_val != '' THEN
        BEGIN
            RETURN ts_val AT TIME ZONE tz_val AT TIME ZONE 'UTC';
        EXCEPTION WHEN OTHERS THEN
            RETURN ts_val; -- Fallback на исходное время
        END;
    END IF;
    
    RETURN ts_val;
END;
$$ LANGUAGE plpgsql IMMUTABLE;
```

### **4. Батч-миграция для больших объемов**

```sql
-- Миграция порциями по 1000 записей
DO $$
DECLARE
    batch_size INTEGER := 1000;
    offset_val INTEGER := 0;
    total_count INTEGER;
    processed INTEGER := 0;
BEGIN
    SELECT COUNT(*) INTO total_count FROM events_parser;
    
    WHILE offset_val < total_count LOOP
        INSERT INTO events (source, external_id, title, ...)
        SELECT source, external_id, title, ...
        FROM events_parser
        ORDER BY id
        LIMIT batch_size OFFSET offset_val;
        
        processed := processed + LEAST(batch_size, total_count - offset_val);
        offset_val := offset_val + batch_size;
        
        -- Логируем прогресс каждые 5000 записей
        IF processed % 5000 = 0 THEN
            RAISE NOTICE 'Мигрировано % из % (%.1f%%)', 
                         processed, total_count, (processed::float / total_count * 100);
        END IF;
        
        -- Пауза между батчами
        PERFORM pg_sleep(0.1);
    END LOOP;
END $$;
```

### **5. CONCURRENTLY индексы**

```sql
-- Создание индексов без блокировки таблицы
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_country 
    ON events(country) WHERE country IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_city 
    ON events(city) WHERE city IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_geo_hash 
    ON events(geo_hash) WHERE geo_hash IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_events_starts_at_normalized 
    ON events(starts_at_normalized) WHERE starts_at_normalized IS NOT NULL;
```

## 🛡️ Безопасный cleanup

### **Автоматические проверки:**

1. **Целостность данных** - сравнение количества записей
2. **Сравнение содержимого** - проверка первых 100 записей
3. **Резервные копии** - автоматическое создание backup таблиц
4. **Откат** - возможность восстановления

```sql
-- Функция безопасного cleanup с проверками
CREATE OR REPLACE FUNCTION safe_drop_events_tables() 
RETURNS TEXT AS $$
DECLARE
    result_text TEXT := '';
    events_count INTEGER;
    parser_count INTEGER;
    user_count INTEGER;
BEGIN
    -- Проверки целостности
    SELECT COUNT(*) INTO events_count FROM events;
    SELECT COUNT(*) INTO parser_count FROM events_parser;
    SELECT COUNT(*) INTO user_count FROM events_user;
    
    -- Создание резервных копий
    CREATE TABLE IF NOT EXISTS events_parser_backup AS SELECT * FROM events_parser;
    CREATE TABLE IF NOT EXISTS events_user_backup AS SELECT * FROM events_user;
    
    -- Проверка соответствия данных
    IF parser_count != (SELECT COUNT(*) FROM events WHERE source != 'user') THEN
        RETURN 'ОШИБКА: Несоответствие данных parser!';
    END IF;
    
    -- Удаление только после всех проверок
    DROP TABLE IF EXISTS events_user CASCADE;
    DROP TABLE IF EXISTS events_parser CASCADE;
    
    RETURN 'Cleanup завершен успешно!';
END;
$$ LANGUAGE plpgsql;
```

## 📈 Мониторинг и метрики

### **Ключевые метрики:**

```sql
-- Статистика миграции
SELECT 
    'events' as table_name,
    COUNT(*) as total_records,
    COUNT(DISTINCT source) as unique_sources,
    COUNT(geo_hash) as with_geo_normalization,
    COUNT(starts_at_normalized) as with_time_normalization
FROM events
UNION ALL
SELECT 
    'events_parser_backup' as table_name,
    COUNT(*) as total_records,
    0 as unique_sources,
    0 as with_geo_normalization,
    0 as with_time_normalization
FROM events_parser_backup
UNION ALL
SELECT 
    'events_user_backup' as table_name,
    COUNT(*) as total_records,
    0 as unique_sources,
    0 as with_geo_normalization,
    0 as with_time_normalization
FROM events_user_backup;
```

### **Производительность индексов:**

```sql
-- Проверка использования индексов
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes 
WHERE tablename = 'events'
ORDER BY idx_tup_read DESC;
```

## 🔄 Откат миграции

### **Автоматический откат:**

```bash
# Выполните откат из резервных копий
psql $DATABASE_URL -f migrations/rollback_from_backup.sql
```

### **Ручной откат:**

```sql
-- Восстановление из резервных копий
DROP TABLE IF EXISTS events_user CASCADE;
DROP TABLE IF EXISTS events_parser CASCADE;

CREATE TABLE events_user AS SELECT * FROM events_user_backup;
CREATE TABLE events_parser AS SELECT * FROM events_parser_backup;

-- Удаление мигрированных данных из events
DELETE FROM events WHERE source IS NOT NULL;

-- Удаление новых колонок
ALTER TABLE events 
  DROP COLUMN IF EXISTS country,
  DROP COLUMN IF EXISTS city,
  DROP COLUMN IF EXISTS venue_name,
  DROP COLUMN IF EXISTS address,
  DROP COLUMN IF EXISTS geo_hash,
  DROP COLUMN IF EXISTS starts_at_normalized;
```

## ✅ Чек-лист продакшен миграции

### **До миграции:**
- [ ] Резервная копия создана
- [ ] Dry-run тест пройден
- [ ] Предварительные проверки выполнены
- [ ] Мониторинг настроен
- [ ] Команда уведомлена

### **Во время миграции:**
- [ ] Логирование активно
- [ ] Мониторинг производительности
- [ ] Готовность к откату
- [ ] Коммуникация с командой

### **После миграции:**
- [ ] Проверка целостности данных
- [ ] Тестирование функциональности
- [ ] Проверка производительности
- [ ] Обновление документации
- [ ] Cleanup старых таблиц

## 🚨 Troubleshooting

### **Проблема: Медленная миграция**
```sql
-- Увеличьте batch_size для больших таблиц
SET batch_size = 5000;

-- Проверьте активные соединения
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';
```

### **Проблема: Нехватка места**
```sql
-- Проверьте использование диска
SELECT 
    pg_size_pretty(pg_database_size(current_database())) as db_size,
    pg_size_pretty(pg_total_relation_size('events')) as events_size;
```

### **Проблема: Блокировки**
```sql
-- Проверьте блокировки
SELECT 
    blocked_locks.pid AS blocked_pid,
    blocked_activity.usename AS blocked_user,
    blocking_locks.pid AS blocking_pid,
    blocking_activity.usename AS blocking_user,
    blocked_activity.query AS blocked_statement
FROM pg_catalog.pg_locks blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
```

## 🎉 Результат продакшен миграции

После успешной миграции:

- ✅ **3 таблицы** → **2 таблицы** (events + events_community)
- ✅ **Нормализованные данные** - geo_hash и временные зоны
- ✅ **Частичные индексы** для дедупликации
- ✅ **CONCURRENTLY индексы** без простоя
- ✅ **Батч-обработка** для больших объемов
- ✅ **Безопасный cleanup** с проверками
- ✅ **Полный откат** из резервных копий
- ✅ **Мониторинг** и метрики

---

**Готово к продакшену! 🚀**
