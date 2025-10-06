# 🚀 Railway Setup Guide

## Обязательные переменные окружения для Railway

Добавьте эти переменные в настройках вашего Railway проекта:

### 1. База данных
```
DATABASE_URL=postgresql://user:password@host:port/database
```

### 2. Telegram Bot
```
TELEGRAM_TOKEN=your_bot_token_from_botfather
```

### 3. Webhook URL
```
WEBHOOK_URL=https://your-railway-app.up.railway.app/webhook
```

### 4. Дополнительные настройки (опционально)
```
GOOGLE_MAPS_API_KEY=your_google_maps_api_key
ADMIN_IDS=123456789,987654321
BOT_RUN_MODE=webhook
GEOCODE_ENABLE=1
DEFAULT_RADIUS_KM=5
KUDAGO_ENABLED=true
BALIFORUM_ENABLE=1
AI_PARSE_ENABLE=1
MOMENTS_ENABLE=0
```

## Как добавить переменные в Railway:

1. Откройте ваш проект в Railway
2. Перейдите в раздел "Variables"
3. Добавьте каждую переменную по отдельности
4. Нажмите "Deploy" для применения изменений

## Проверка конфигурации:

После добавления переменных запустите:
```bash
python validate_config.py
```

Этот скрипт проверит все обязательные переменные и загрузит конфигурацию.

## Устранение проблем:

Если деплой падает с ошибкой "DATABASE_URL is required":
1. Убедитесь, что переменная `DATABASE_URL` добавлена в Railway
2. Проверьте, что URL базы данных корректный
3. Убедитесь, что база данных PostgreSQL подключена к проекту

## Готово! 🎉

После настройки всех переменных ваш бот должен успешно деплоиться и работать.
