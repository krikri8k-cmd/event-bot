# 📊 Руководство по мониторингу KudaGo

## 🏥 Health-эндпоинты

### Основные эндпоинты

- **`/api/v1/health/kudago`** - Основной health-чек
- **`/api/v1/health/kudago/metrics`** - Метрики в формате Prometheus
- **`/api/v1/health/kudago/status`** - Простой статус для алертов

### Запуск health-сервера

```bash
# Локально
python web/server.py

# Или через uvicorn
uvicorn web.server:app --host 0.0.0.0 --port 8080
```

## 📈 Ключевые метрики

### Статусы системы

- **`ok`** - error_rate < 2% и events_received > 0
- **`degraded`** - 2-10% ошибок или 0 событий при ≥1 успешном запросе
- **`down`** - 100% ошибок за 5 мин или нет успешных запросов 10 мин

### Критерии Go/No-Go

**✅ Можно включать `KUDAGO_DRY_RUN=false` если:**

- error_rate < 5% за 24-48 часов
- cache_hit_rate > 50% после первого часа
- p95 latency < 2s
- ≥ 20 уникальных событий/день на город
- никаких жалоб в логах бота

**❌ НЕ включать если:**

- error_rate > 10% за 5 минут
- events_received == 0 при наличии запросов 10 минут
- p95 request_duration_ms > 3000ms 10 минут

## 🔍 Что смотреть в логах

### Примеры событий (проверить качество)

```json
{
  "title": "Концерт группы X",
  "place": {"title": "Клуб Y", "address": "ул. Z, 1"},
  "dates": [{"start": 1640995200, "end": 1640998800}],
  "lat": 55.7558,
  "lon": 37.6173,
  "site_url": "https://kudago.com/msk/event/..."
}
```

### Проверки

1. **Заголовки**: непустые, ≤ 180 символов
2. **Время**: start_ts соответствует Europe/Moscow
3. **Координаты**: lat/lon в пределах города
4. **URL**: https://kudago.com/...
5. **Гео-фильтр**: events_received vs events_after_geo ≈ 90-100%

## 🚨 Алерты

### Критические

- `error_rate > 10%` 5 минут
- `events_received == 0` при наличии запросов 10 минут
- `no_successful_requests_10min`

### Предупреждения

- `high_latency > 3000ms` 10 минут
- `cache_hit_rate < 50%` 1 час

## 🔧 План отката

### Мгновенный откат

```bash
# Отключить KudaGo полностью
KUDAGO_ENABLED=false

# Отключить гео-фильтр (если нужно)
ENABLE_GEO_BOUNDS=false
```

### Проверка после отката

1. Бали события работают как раньше
2. Команда `/today` показывает "Источник недоступен"
3. Логи без ошибок

## 📊 Prometheus метрики

```prometheus
# Счетчики
kudago_requests_total
kudago_api_errors_total
kudago_events_received_total
kudago_events_after_geo_total
kudago_cache_hits_total

# Gauge
kudago_rps_current
kudago_avg_latency_ms
kudago_error_rate_percent
kudago_last_success_timestamp
```

## 🧪 Тестирование

### Локальное тестирование

```bash
# Запуск health-сервера
python web/server.py

# Проверка эндпоинтов
curl http://localhost:8080/api/v1/health/kudago
curl http://localhost:8080/api/v1/health/kudago/metrics
curl http://localhost:8080/api/v1/health/kudago/status
```

### Тестирование валидатора

```python
from utils.event_validator import validate_event, get_validation_summary

# Тестовое событие
test_event = {
    "title": "Тестовое событие",
    "start_ts": 1640995200,
    "lat": 55.7558,
    "lng": 37.6173,
    "source_url": "https://kudago.com/msk/event/123"
}

validated = validate_event(test_event, "moscow")
print(get_validation_summary())
```

## 📝 Логирование

### Уровни логов

- **INFO**: Успешные запросы, статистика
- **WARNING**: Проблемы с валидацией, гео-фильтром
- **ERROR**: Ошибки API, критические проблемы
- **DEBUG**: Детальная отладка

### Ключевые сообщения

```
✅ Найдено X событий в Москва
📍 Выбран город: Москва (msk)
Валидация msk: X/Y событий прошли валидацию
DRY_RUN: fetched=X normalized=Y after_geo=Z
```

## 🔄 Обновление конфигурации

### ENV переменные

```bash
# Основные
KUDAGO_ENABLED=true
KUDAGO_DRY_RUN=false

# Настройки API
KUDAGO_RPS=3
KUDAGO_TIMEOUT_S=8
KUDAGO_PAGE_SIZE=100

# Лимиты
TODAY_MAX_EVENTS=60
TODAY_SHOW_TOP=12
CACHE_TTL_S=300

# Health сервер
HEALTH_HOST=0.0.0.0
HEALTH_PORT=8080
```

### Перезапуск после изменений

```bash
# Перезапуск бота
systemctl restart event-bot

# Проверка статуса
curl http://localhost:8080/api/v1/health/kudago
```
