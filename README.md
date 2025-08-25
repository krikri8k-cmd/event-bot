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
```bash
pip install -r requirements.txt
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

### 3. Запуск бота
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

## 🤝 Вклад в проект

1. Форкните репозиторий
2. Создайте ветку для новой функции
3. Внесите изменения
4. Создайте Pull Request

## 📄 Лицензия

MIT License

---

**Создано с ❤️ для поиска лучших событий в Индонезии!**
