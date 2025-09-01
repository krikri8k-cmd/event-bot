![CI](https://github.com/krikri8k-cmd/event-bot/actions/workflows/ci.yml/badge.svg)

# 🎫 EventBot - Telegram Bot для поиска событий

Умный Telegram бот для поиска и рекомендации событий в Индонезии с поддержкой AI генерации.

## ✨ Возможности

- 🔍 **Поиск событий** по геолокации
- 🤖 **AI генерация** событий через GPT
- 📍 **Популярные места** и достопримечательности
- 🌐 **Интеграция с API** (Eventbrite, Meetup, Timepad)
- 💾 **База данных** для сохранения событий
- 🗺️ **Google Maps** интеграция

## 🚀 Быстрый старт

### 1. Установка зависимостей

#### Linux/macOS:
```bash
pip install -r requirements.txt
```

#### Windows (фикс lxml):
Если установка валится на сборке `lxml`:
```powershell
# активируй venv
.venv\Scripts\Activate.ps1

# предварительно поставь бинарный lxml и затем зависимости
pip install "lxml>=5.2.1" --only-binary=:all:
$env:PIP_ONLY_BINARY = "lxml"
pip install -r requirements.txt
Remove-Item Env:\PIP_ONLY_BINARY
```

**Проверка:**
```powershell
python -c "import lxml, sys; print('lxml:', lxml.__version__, '| python:', sys.version)"
```

### 2. Настройка переменных окружения
Скопируйте `env.local.template` в `.env.local` и заполните:
```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token

# OpenAI
OPENAI_API_KEY=your_openai_key
OPENAI_ORGANIZATION=your_org_id

# Google Maps
GOOGLE_MAPS_API_KEY=your_google_maps_key

# Database
DATABASE_URL=postgresql://user:password@host:port/database

# Event Aggregators
EVENTBRITE_API_KEY=your_eventbrite_public_token

# Settings
DEFAULT_RADIUS_KM=5
ADMIN_IDS=123456,789012
```

### 2.1 Подключение к Railway

Для подключения к базе данных Railway используйте:

**Для Python (SQLAlchemy):**
```bash
DATABASE_URL=postgresql+psycopg2://postgres:<PASSWORD>@interchange.proxy.rlwy.net:23764/railway?sslmode=require
```

**Для psql/CLI:**
```bash
DATABASE_URL_PSQL=postgresql://postgres:<PASSWORD>@interchange.proxy.rlwy.net:23764/railway?sslmode=require
```

**Важно:** 
- Используйте публичный host/port из Railway
- Обязательно добавьте `?sslmode=require`
- Пароль должен быть URL-экранирован, если содержит специальные символы

### 3. Проверка окружения

Перед запуском бота рекомендуется проверить настройки:

```powershell
# активируй venv
.venv\Scripts\Activate.ps1

# проверка окружения
python scripts\checks\verify_env.py

# проверка БД
python scripts\checks\verify_db.py

# dry-run AI ingest (без записи) — отработку и логи оценить глазами
python -m api.ingest.ai_ingest --limit 3 --dry-run
```

### 4. Запуск бота
```bash
python bot_enhanced_v3.py
```

## 📁 Структура проекта

```
event-bot/
├── bot_enhanced_v3.py      # Главный файл бота
├── config.py               # Конфигурация и настройки
├── database.py             # Работа с базой данных
├── event_apis.py           # API агрегаторов событий
├── enhanced_event_search.py # Улучшенный поиск событий
├── smart_ai_generator.py   # AI генерация событий
├── ai_utils.py             # Утилиты для работы с AI
├── utils/
│   └── geo_utils.py        # Географические утилиты
├── requirements.txt        # Зависимости Python
├── .gitignore             # Игнорируемые файлы
└── README.md              # Документация
```

## 🎯 Основные команды бота

- `/start` - Начать работу с ботом
- `/help` - Показать справку
- `/location` - Отправить геолокацию для поиска событий
- `/events` - Показать последние найденные события
- `/generate` - Сгенерировать события через AI

## 🔧 Технологии

- **Python 3.13+**
- **aiogram 3.x** - Telegram Bot API
- **SQLAlchemy** - ORM для базы данных
- **OpenAI GPT** - AI генерация
- **Google Maps API** - Геолокация и карты
- **httpx** - Асинхронные HTTP запросы

## 📚 Документация

Подробная документация по обновлениям и настройке в файле `UPDATE_INSTRUCTIONS.md`.

## Apply SQL (event_sources + indexes)

### Locally (Linux/Mac)
```bash
export DATABASE_URL="postgresql+psycopg2://USER:PASS@HOST:5432/DBNAME"
make db-apply
```

### Locally (Windows PowerShell)
```powershell

## 📍 Геолокация и поиск событий

### Команды для работы с локацией:

- **`/set_location`** - установить свою геолокацию
- **`/radius 10`** - установить радиус поиска (в км, от 1 до 100)
- **`/nearby`** - найти события рядом с сохраненной локацией

### Как это работает:

1. **Отправьте геолокацию** командой `/set_location` или нажав кнопку "📍 Что рядом"
2. **Установите радиус** командой `/radius 15` (по умолчанию 10 км)
3. **Ищите события** командой `/nearby` или кнопкой "📍 Что рядом"

### Фильтрация событий:

- ✅ **Строгая фильтрация по радиусу** - показываются только события в указанном радиусе
- ✅ **Региональная фильтрация** - если включен `STRICT_REGION_FILTER`, события ограничиваются регионом (например, только Бали)
- ✅ **Сохранение настроек** - ваша локация и радиус сохраняются в базе данных
- ✅ **Точные расстояния** - каждое событие показывает точное расстояние до вас

### Примеры использования:

```
/radius 5    # Поиск в радиусе 5 км
/radius 20   # Поиск в радиусе 20 км
/nearby      # Найти события рядом
```

### Настройки в .env.local:

```bash
# Геолокация и фильтрация
DEFAULT_RADIUS_KM=5
STRICT_REGION_FILTER=1
GEO_REGION_BBOXES={"bali":{"min_lat":-8.9,"max_lat":-8.1,"min_lon":114.4,"max_lon":115.9}}
```
$Env:DATABASE_URL="postgresql+psycopg2://USER:PASS@HOST:5432/DBNAME"
python scripts\apply_sql.py sql\2025_ics_sources_and_indexes.sql
# или:
powershell -File scripts\db_apply.ps1
```

### Verify
```bash
python - << 'PY'
import os
from sqlalchemy import create_engine, text
eng = create_engine(os.environ["DATABASE_URL"], future=True)
with eng.begin() as c:
    cols = c.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='event_sources'"
    )).all()
print("event_sources columns:", [r[0] for r in cols])
PY
```

### OAuth Meetup (локально)

1) Запусти API:
   ```bash
   uvicorn api.app:app --reload --port 8000
   ```

2) Открой ссылку на логин:
   ```bash
   GET http://localhost:8000/oauth/meetup/login
   ```
   → вернётся JSON с "authorize_url".

3) Перейди по `authorize_url`, залогинься в Meetup.
   После логина тебя вернёт на:
   ```
   http://localhost:8000/oauth/meetup/callback?code=...
   ```

4) Эндпоинт обменяет `code` на токены и вернёт превью токенов.
   ПОЛНЫЕ значения токенов смотри в логах uvicorn:
   ```
   MEETUP_ACCESS_TOKEN=...
   MEETUP_REFRESH_TOKEN=...
   ```

5) Скопируй оба значения в `.env.local`:
   ```
   MEETUP_ACCESS_TOKEN=...
   MEETUP_REFRESH_TOKEN=...
   ```

6) Теперь источники Meetup работают с авторизацией.

## Meetup (фиче-флаг)

По умолчанию интеграция Meetup выключена.

**Включить:**
```bash
# .env.local
MEETUP_ENABLED=1
# опционально для мок-режима callback:
# MEETUP_MOCK=1
```

Эндпоинты `/oauth/meetup/*` и любые источники Meetup будут доступны только при `MEETUP_ENABLED=1`.

### Meetup OAuth — мок-режим (dev)

Для быстрой локальной проверки OAuth-колбэка используйте мок-режим:
```bash
export MEETUP_MOCK=1
uvicorn api.app:app --reload --port 8000
# затем:
# http://localhost:8000/oauth/meetup/callback?code=test123&state=xyz
```

**Ожидаемый ответ:**

```json
{"ok": true, "code": "test123", "state": "xyz", "mock": true}
```

**Боевой режим** (обмен code→tokens) включается автоматически, когда переменная `MEETUP_MOCK` не установлена.

**Redirect URL для Meetup (локально):**

```
http://localhost:8000/oauth/meetup/callback
```

## 🤝 Вклад в проект

1. Форкните репозиторий
2. Создайте ветку для новой функции
3. Внесите изменения
4. Создайте Pull Request

## 📄 Лицензия

MIT License

## 🗄️ DB Apply (manual)

Применить SQL к БД через GitHub Actions:

1. Перейди в **Actions** → выбери **DB Apply (manual)**.
2. Нажми **Run workflow**.
3. В `sql_path` оставь по умолчанию `sql/2025_ics_sources_and_indexes.sql` (или укажи нужный файл).
4. Подтверди **Run workflow** и жди зелёный статус.

> Важно: строка подключения берётся из `Settings → Secrets and variables → Actions → DATABASE_URL`.

### GitHub Actions: DATABASE_URL

- При редактировании секрета поле Value **пустое** — это норма (write-only).
- Секрет должен быть задан в Settings → Secrets and variables → Actions (и в Environments, если job использует `environment:`).
- Формат для Railway:
  `postgresql://postgres:<PASSWORD>@interchange.proxy.rlwy.net:23764/railway?sslmode=require`
- Для smoke-теста можно использовать:
  `psql "$DATABASE_URL" -c "select current_database();"`

---

**Создано с ❤️ для поиска лучших событий в Индонезии!**
