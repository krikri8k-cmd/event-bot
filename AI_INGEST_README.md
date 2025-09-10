# 🤖 AI-пайплайн парсинга событий

Автоматический пайплайн для извлечения событий из веб-страниц с помощью LLM и загрузки в базу данных.

## 🎯 Что делает

1. **Скачивает страницы** из списка источников
2. **Извлекает события** через OpenAI GPT
3. **Нормализует время** и таймзоны
4. **Геокодирует адреса** в координаты
5. **Дедуплицирует** события
6. **Upsert в БД** с уникальными индексами

## 📁 Структура

```
api/
├── ai_extractor.py      # Извлечение через LLM
├── normalize.py         # Нормализация времени и геокодинг
└── ingest/
    └── ai_ingest.py     # Основной пайплайн

seeds/
└── ai_sources.json      # Источники для парсинга

.github/workflows/
└── ai-ingest.yml        # GitHub Actions
```

## ⚙️ Настройка

### 1. Переменные окружения

Добавьте в `.env.local`:

```bash
# OpenAI
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4o-mini

# Таймзона
DEFAULT_TZ=Asia/Makassar

# Геокодинг
GEOCODE_URL=https://nominatim.openstreetmap.org/search
GEOCODE_EMAIL=your@email.com

# Поведение
AI_INGEST_ENABLED=1
AI_INGEST_SOURCE_TAG=ai
AI_INGEST_MAX_URLS=20
AI_INGEST_MAX_EVENTS_PER_URL=20
```

### 2. GitHub Secrets

В GitHub → Settings → Secrets → Actions добавьте:

- `OPENAI_API_KEY` - ваш ключ OpenAI
- `DATABASE_URL` - строка подключения к БД
- `GEOCODE_EMAIL` - email для User-Agent (опционально)

### 3. Источники

Отредактируйте `seeds/ai_sources.json`:

```json
[
  {"url": "https://real-site.com/events", "region": "bali", "city": "Kuta"},
  {"url": "https://another-site.com/calendar", "region": "bali", "city": "Canggu"}
]
```

## 🚀 Запуск

### Ручной запуск

```bash
python -m api.ingest.ai_ingest
```

### GitHub Actions

1. Перейдите в **Actions** → **AI Ingest (manual/cron)**
2. Нажмите **Run workflow**
3. Дождитесь завершения

### По расписанию

Пайплайн запускается автоматически каждый день в 03:18 UTC.

## 📊 Результаты

После запуска проверьте:

```sql
-- Количество событий из AI-парсинга
SELECT COUNT(*) FROM events WHERE source='ai';

-- Последние события
SELECT title, starts_at, city, lat, lng 
FROM events 
WHERE source='ai' 
ORDER BY created_at DESC 
LIMIT 5;
```

## 🔧 Тестирование в боте

1. Отправьте боту геолокацию (например, Кута, Бали)
2. Используйте команду `/nearby`
3. Должны появиться реальные события из БД

## ⚠️ Важные замечания

- **Уважайте ToS сайтов** и robots.txt
- **Частота запросов** невысокая
- **User-Agent** корректный
- **Не изобретаем события** - только извлекаем из текста
- **ICS календари** предпочтительнее AI-парсинга

## 🐛 Отладка

Логи показывают:
- `[OK] URL -> N events` - успешно обработано
- `[ERR] URL: error` - ошибка при обработке

Проверьте:
- Доступность URL
- Валидность OpenAI API ключа
- Подключение к БД
- Формат JSON в ai_sources.json
