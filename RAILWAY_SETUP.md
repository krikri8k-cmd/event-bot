# 🚀 Настройка Railway для EventBot

## 📋 Переменные окружения для Railway

В Railway нужно настроить следующие переменные окружения:

### 🔑 Обязательные переменные:

1. **TELEGRAM_TOKEN**
   - Ваш токен Telegram бота от @BotFather
   - Пример: `7369401579:AAGYu3kAzPehfAb9YlAEyMtb0YZ1yy9ftNI`

2. **DATABASE_URL**
   - URL базы данных PostgreSQL
   - Railway автоматически создаст эту переменную
   - Пример: `postgresql://postgres:password@host:port/database`

3. **OPENAI_API_KEY**
   - Ваш API ключ OpenAI
   - Получите на [platform.openai.com/account/api-keys](https://platform.openai.com/account/api-keys)
   - Пример: `sk-proj-...`

4. **GOOGLE_MAPS_API_KEY**
   - Ваш API ключ Google Maps
   - Получите на [console.cloud.google.com](https://console.cloud.google.com)
   - Пример: `AIzaSy...`

### 🔧 Дополнительные переменные:

5. **GOOGLE_APPLICATION_CREDENTIALS**
   - Путь к файлу с ключами Google Cloud
   - Значение: `gcp-key.json`

6. **DEFAULT_RADIUS_KM**
   - Радиус поиска событий в километрах
   - Рекомендуемое значение: `4`

## 🛠️ Как настроить в Railway:

1. **Откройте проект в Railway**
2. **Перейдите в раздел "Variables"**
3. **Добавьте каждую переменную:**

```
TELEGRAM_TOKEN=your_telegram_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here
GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
GOOGLE_APPLICATION_CREDENTIALS=gcp-key.json
DEFAULT_RADIUS_KM=4
```

4. **DATABASE_URL создастся автоматически** при добавлении PostgreSQL

## 📁 Файлы для загрузки:

1. **gcp-key.json** - загрузите в Railway как файл
2. **Все Python файлы** - загрузите в GitHub

## 🔄 Обновление кода:

После настройки переменных Railway автоматически перезапустит бота с новыми настройками.

## ✅ Проверка:

1. Бот должен ответить на `/start`
2. Поиск событий должен работать
3. AI генерация должна функционировать
