# 🚂 Деплой Event Bot на Railway

## ✅ Что уже готово

1. **railway.json** - конфигурация для Railway
2. **requirements.txt** - все зависимости
3. **runtime.txt** - версия Python 3.13.7
4. **env.local.railway** - шаблон переменных окружения

## 📋 Пошаговая инструкция

### 1. Подготовка файлов
```bash
# Переименуй файл с переменными окружения
mv env.local.railway .env.local
```

### 2. Настройка в Railway Dashboard

#### Создание проекта:
1. Зайди на [railway.app](https://railway.app)
2. Создай новый проект
3. Подключи GitHub репозиторий

#### Добавление PostgreSQL:
1. В проекте нажми "New Service" → "Database" → "PostgreSQL"
2. Railway автоматически создаст переменные:
   - `PGUSER`
   - `POSTGRES_PASSWORD` 
   - `RAILWAY_PRIVATE_DOMAIN`
   - `PGDATABASE`

#### Настройка переменных окружения:
1. В настройках проекта перейди в "Variables"
2. Добавь следующие переменные:

```
TELEGRAM_TOKEN=твой_токен_бота
OPENAI_API_KEY=твой_openai_ключ (опционально)
GOOGLE_MAPS_API_KEY=твой_google_maps_ключ (опционально)
DEFAULT_RADIUS_KM=4
ADMIN_IDS=твой_telegram_id
```

### 3. Деплой

1. Railway автоматически определит что это Python проект
2. Использует `railway.json` для конфигурации
3. Запустит `python bot.py` как указано в `startCommand`

## 🔧 Проверка конфигурации

Запусти тестовый скрипт локально:
```bash
python test_db.py
```

## 🚨 Возможные проблемы

### Ошибка "password authentication failed"
- Убедись что в Railway правильно настроены переменные PostgreSQL
- Проверь что `DATABASE_URL` использует `RAILWAY_PRIVATE_DOMAIN`

### Ошибка "Module not found"
- Проверь что все зависимости в `requirements.txt`
- Railway автоматически установит их

### Бот не отвечает
- Проверь логи в Railway Dashboard
- Убедись что `TELEGRAM_TOKEN` правильный
- Проверь что бот не заблокирован

## 📊 Мониторинг

- Логи доступны в Railway Dashboard
- Метрики использования в разделе "Metrics"
- Автоматический рестарт при сбоях

## 💰 Стоимость

- **$5/месяц** - план Hobby
- Включает до 8 ГБ RAM / 8 vCPU
- PostgreSQL база данных
- Глобальные регионы

## 🎉 Готово!

После деплоя твой бот будет доступен 24/7 на Railway! 🚂✨
