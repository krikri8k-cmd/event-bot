# Система автоматического сбора событий

Система для автоматического сбора событий из бесплатных и легальных источников в Индонезии (Бали/Джакарта).

## Возможности

- **ICS-календари**: Парсинг публичных ICS-файлов
- **Nexudus-сайты**: Автоматическое извлечение ICS-ссылок со страниц событий
- **Планировщик**: APScheduler для автоматического сбора каждые 5 минут
- **Админ-панель**: API для управления источниками
- **Безопасные тесты**: Легкие юнит-тесты и FULL-тесты с БД

## Установка

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Примените миграции БД:
```bash
python apply_sql.py
```

## Конфигурация

1. Скопируйте `.env.local.template` в `.env.local`
2. Настройте переменные:
```bash
# Ingest scheduler
INGEST_DEFAULT_FREQ_MIN=120  # частота обновления по умолчанию (минуты)
INGEST_MAX_FAILS=5           # максимальное количество ошибок перед отключением
```

3. Добавьте источники в `config/sources.seed.json`:
```json
[
  {
    "type": "ics",
    "url": "https://example.com/calendar.ics",
    "region": "bali",
    "enabled": true,
    "freq_minutes": 180,
    "notes": "Публичный календарь событий"
  }
]
```

## Использование

### Запуск API с планировщиком

```bash
uvicorn api.app:app --reload
```

Планировщик автоматически запустится при старте приложения.

### Админ-эндпоинты

- `GET /admin/sources` - список источников
- `POST /admin/sources` - добавить/обновить источник
- `POST /admin/sources/{id}/toggle` - включить/выключить источник
- `POST /admin/ingest/run` - запустить сбор вручную

### Примеры запросов

Добавить ICS-источник:
```bash
curl -X POST "http://localhost:8000/admin/sources" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "ics",
    "url": "https://example.com/events.ics",
    "region": "bali",
    "enabled": true,
    "freq_minutes": 120
  }'
```

Добавить Nexudus-источник:
```bash
curl -X POST "http://localhost:8000/admin/sources" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "html_nexudus",
    "url": "https://bworkbali.spaces.nexudus.com/en/events",
    "region": "bali",
    "enabled": true,
    "freq_minutes": 240
  }'
```

## Тестирование

### Юнит-тесты (без БД)
```bash
python -m pytest tests/test_ics_parse_unit.py -v
```

### FULL-тесты (с БД)
```bash
FULL_TESTS=1 python -m pytest tests/test_ingest_cycle_api.py -v
```

## Структура проекта

```
├── sql/2025_ics_sources_and_indexes.sql  # Миграции БД
├── sources/
│   ├── common.py                         # Общие функции
│   ├── ics.py                           # ICS-парсер
│   └── nexudus.py                       # Nexudus-парсер
├── ingest/
│   └── upsert.py                        # Upsert в БД
├── api/
│   └── admin.py                         # Админ-эндпоинты
├── scheduler.py                         # Планировщик
├── apply_sql.py                         # Применение миграций
└── tests/
    ├── test_ics_parse_unit.py           # Юнит-тесты
    └── test_ingest_cycle_api.py         # FULL-тесты
```

## Мониторинг

Система автоматически:
- Отслеживает статус источников
- Отключает источники после 5 ошибок
- Логирует количество обработанных событий
- Поддерживает ETag/Last-Modified для оптимизации

## Безопасность

- Все источники проверяются на валидность
- Ограничения на количество запросов
- Таймауты для HTTP-запросов
- Graceful handling ошибок
