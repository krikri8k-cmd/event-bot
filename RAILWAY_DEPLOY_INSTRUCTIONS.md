# 🚀 Инструкция по деплою в Railway

## ✅ Подготовка завершена

Все файлы для деплоя готовы:
- ✅ `Dockerfile` - обновлен для Railway
- ✅ `railway-bot-start.sh` - скрипт с keep-alive
- ✅ `bot_health.py` - health check сервер
- ✅ `railway.env.template` - шаблон переменных окружения
- ✅ Интеграция health check в основной бот

## 🚀 Шаги деплоя

### 1. Подготовка кода
```bash
# Убедись что все изменения закоммичены
git add .
git commit -m "feat: add Railway deployment with moments and radius buttons"
git push
```

### 2. Создание сервиса в Railway

1. **Зайди в Railway** (https://railway.app)
2. **Создай новый проект** или выбери существующий
3. **Добавь новый сервис** → "Deploy from GitHub repo"
4. **Выбери репозиторий** с event-bot
5. **Настрой деплой**:
   - **Build Command**: `docker build -f Dockerfile -t event-bot .`
   - **Start Command**: `./railway-bot-start.sh`
   - **Root Directory**: `./` (корень репозитория)

### 3. Настройка переменных окружения

В Railway Variables добавь:

#### Обязательные:
```
TELEGRAM_TOKEN=your_bot_token_here
DATABASE_URL=postgresql://user:password@host:port/database
```

#### Рекомендуемые:
```
# Bot settings
BOT_RUN_MODE=webhook
WEBHOOK_URL=https://your-railway-app.up.railway.app/webhook

# Radius settings
DEFAULT_RADIUS_KM=5
RADIUS_STEP_KM=5
MAX_RADIUS_KM=15

# Moments settings
MOMENTS_ENABLE=1
MOMENT_TTL_OPTIONS="30,60,120"
MOMENT_DAILY_LIMIT=2
MOMENT_MAX_RADIUS_KM=20

# AI settings
AI_PARSE_ENABLE=1
AI_GENERATE_SYNTHETIC=0
STRICT_SOURCE_ONLY=0

# Admin IDs
ADMIN_IDS=your_telegram_id
```

#### Опциональные:
```
# Google Maps
GOOGLE_MAPS_API_KEY=your_google_maps_api_key

# OpenAI
OPENAI_API_KEY=your_openai_api_key
OPENAI_ORGANIZATION=your_organization_id

# Eventbrite
EVENTBRITE_API_KEY=your_eventbrite_api_key

# Meetup
MEETUP_API_KEY=your_meetup_api_key
```

### 4. Деплой

1. **Нажми "Deploy"** в Railway
2. **Дождись сборки** (может занять 2-5 минут)
3. **Проверь логи** на наличие:
   ```
   🚀 Запуск EventBot на Railway...
   ✅ Health check сервер запущен на порту 8000
   🤖 Запуск Telegram бота...
   Запуск улучшенного EventBot (aiogram 3.x)...
   ```

### 5. Проверка работы

#### Health Check:
Открой URL Railway + `/health`:
```json
{
  "status": "healthy",
  "service": "EventBot Telegram Bot",
  "timestamp": 1234567890,
  "uptime": "running"
}
```

#### Ping Endpoint:
URL Railway + `/ping`:
```json
{"pong": 1234567890}
```

#### Telegram бот:
1. Отправь `/start` боту
2. Проверь кнопку "🔧 Настройки радиуса"
3. Проверь кнопку "⚡ Создать Момент"
4. Отправь геолокацию и проверь поиск

## 🔧 Настройка webhook (опционально)

Если хочешь использовать webhook вместо polling:

1. **Получи URL** твоего Railway сервиса
2. **Установи webhook**:
   ```bash
   curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
        -H "Content-Type: application/json" \
        -d '{"url": "https://your-railway-app.up.railway.app/webhook"}'
   ```

## 📊 Мониторинг

### Логи Railway:
- Следи за логами в Railway UI
- Ищи сообщения о keep-alive каждые 5 минут
- Проверяй ошибки подключения к Telegram

### Health Check:
- Railway автоматически проверяет `/health` endpoint
- Keep-alive предотвращает "засыпание" сервиса
- Health check endpoints доступны для внешнего мониторинга

### UptimeRobot (рекомендуется):
1. Создай аккаунт на https://uptimerobot.com
2. Добавь мониторинг URL Railway + `/health`
3. Настрой проверку каждые 5 минут
4. Получай уведомления о проблемах

## 🚨 Troubleshooting

### Бот не отвечает:
1. Проверь логи Railway
2. Убедись что `TELEGRAM_TOKEN` правильный
3. Проверь что health check работает
4. Проверь подключение к базе данных

### Health check не работает:
1. Проверь что порт 8000 открыт
2. Убедись что health check сервер запустился
3. Проверь логи на ошибки

### Railway усыпляет сервис:
1. Убедись что keep-alive работает
2. Проверь что health check endpoints отвечают
3. Настрой UptimeRobot для внешнего мониторинга
4. Рассмотри платный план Railway

### Ошибки базы данных:
1. Проверь `DATABASE_URL`
2. Убедись что база данных доступна
3. Проверь миграции

## 🎉 Результат

После успешного деплоя у тебя будет:
- ✅ **Бот работает 24/7** на Railway
- ✅ **Health check endpoints** доступны
- ✅ **Keep-alive** предотвращает "засыпание"
- ✅ **Моменты** с лимитами и TTL
- ✅ **Кнопки радиуса** 5/10/15 км
- ✅ **Автоматический перезапуск** при ошибках

## 🔄 Обновления

Для обновления бота:
1. Внеси изменения в код
2. Закоммить и запушь в GitHub
3. Railway автоматически пересоберет и перезапустит сервис
4. Проверь логи на успешный запуск

---
*Готово к деплою: 2024*  
*Аниме-разработчица: Railway готов к новым приключениям! (◕‿◕)✨*
