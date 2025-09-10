# 🚀 Деплой Telegram бота на Railway

## Проблема
Бот засыпает на Railway из-за отсутствия активности. Railway "усыпляет" неактивные сервисы.

## Решение
Запускаем Telegram бота с health check сервером и keep-alive механизмом.

## Файлы для деплоя

### 1. Dockerfile.bot
Специальный Dockerfile для Telegram бота:
```dockerfile
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY . .
RUN chmod +x railway-bot-start.sh
CMD ["./railway-bot-start.sh"]
```

### 2. railway-bot-start.sh
Скрипт запуска с keep-alive:
```bash
#!/bin/bash
# Keep-alive каждые 5 минут
keep_alive() {
    while true; do
        echo "$(date): 🔄 Keep-alive ping..."
        sleep 300
    done
}
keep_alive &
python bot_enhanced_v3.py
```

### 3. bot_health.py
Health check сервер для Railway:
- `/health` - статус бота
- `/ping` - keep-alive endpoint
- Работает на порту 8000

## Инструкция по деплою

### Шаг 1: Подготовка
```bash
# Убедись что все файлы закоммичены
git add .
git commit -m "feat: add Railway bot deployment files"
git push
```

### Шаг 2: Настройка Railway
1. **Создай новый сервис** в Railway
2. **Выбери "Build via Dockerfile"**
3. **Укажи Dockerfile.bot** как путь к Dockerfile
4. **Root Directory** = `./` (корень репозитория)

### Шаг 3: Переменные окружения
Добавь в Railway Variables:
```
TELEGRAM_TOKEN=your_bot_token
DATABASE_URL=your_database_url
MEETUP_ENABLED=0
```

### Шаг 4: Деплой
1. Нажми **"Deploy"**
2. Дождись успешной сборки
3. Проверь логи на наличие:
   ```
   🚀 Запуск EventBot на Railway...
   Health check сервер запущен на порту 8000
   Запуск улучшенного EventBot (aiogram 3.x)...
   ```

## Проверка работы

### 1. Health Check
Открой URL Railway + `/health`:
```json
{
  "status": "healthy",
  "service": "EventBot Telegram Bot",
  "timestamp": 1234567890,
  "uptime": "running"
}
```

### 2. Ping Endpoint
URL Railway + `/ping`:
```json
{"pong": 1234567890}
```

### 3. Telegram бот
Отправь `/start` боту - должен ответить сразу!

## Мониторинг

### Логи Railway
- Следи за логами в Railway UI
- Ищи сообщения о keep-alive
- Проверяй ошибки подключения к Telegram

### Keep-Alive
- Бот автоматически отправляет ping каждые 5 минут
- Railway видит активность и не усыпляет сервис
- Health check endpoints доступны для мониторинга

## Troubleshooting

### Бот не отвечает
1. Проверь логи Railway
2. Убедись что TELEGRAM_TOKEN правильный
3. Проверь что health check работает

### Health check не работает
1. Проверь что порт 8000 открыт
2. Убедись что aiohttp установлен
3. Проверь логи на ошибки

### Railway усыпляет сервис
1. Убедись что keep-alive работает
2. Проверь что health check endpoints отвечают
3. Рассмотри платный план Railway

## Альтернативы

### 1. UptimeRobot
- Бесплатный мониторинг каждые 5 минут
- Автоматически пингует `/health` endpoint

### 2. Cron-job.org
- Бесплатные cron задачи
- Настрой ping каждые 5 минут на `/ping`

### 3. Платный план Railway
- Нет ограничений на "засыпание"
- Постоянная работа сервиса

## Результат
✅ Бот работает 24/7 на Railway  
✅ Health check endpoints доступны  
✅ Keep-alive предотвращает "засыпание"  
✅ Автоматический перезапуск при ошибках  

Теперь твой бот будет работать всегда! 🎉
