# 🔐 Руководство по тестированию OAuth Meetup

## ✅ Предварительная проверка

### 1. Проверка готовности системы
```bash
# Проверяем что API импортируется
python -c "from api.app import app; print('✅ API готов')"

# Проверяем OAuth менеджер
python -c "from api.oauth_meetup import MeetupOAuth; print('✅ OAuth готов')"

# Проверяем источник Meetup
python -c "from sources.meetup import fetch; print('✅ Источник готов')"
```

### 2. Запуск API сервера
```bash
uvicorn api.app:app --reload --port 8000
```

### 3. Проверка базовых эндпоинтов
```bash
# Проверяем health
curl http://localhost:8000/health
# Ожидаем: {"status":"ok"}

# Проверяем OAuth login без настроек
curl http://localhost:8000/oauth/meetup/login
# Ожидаем: {"detail":"MEETUP_CLIENT_ID is not configured"}

# Проверяем OAuth callback без параметров
curl http://localhost:8000/oauth/meetup/callback
# Ожидаем: {"detail":[{"type":"missing","loc":["query","code"],"msg":"Field required"}]}
```

## 🚀 Полное тестирование OAuth флоу

### Шаг 1: Настройка OAuth приложения в Meetup
1. Зайти на https://www.meetup.com/api/oauth/list/
2. Создать новое OAuth приложение
3. Указать Redirect URI: `http://localhost:8000/oauth/meetup/callback`
4. Скопировать Client ID и Client Secret

### Шаг 2: Настройка локального окружения
```bash
# Создать .env.local из шаблона
cp env.local.template .env.local

# Добавить в .env.local:
MEETUP_CLIENT_ID=your_client_id_here
MEETUP_CLIENT_SECRET=your_client_secret_here
MEETUP_REDIRECT_URI=http://localhost:8000/oauth/meetup/callback
```

### Шаг 3: Получение authorize_url
```bash
# Перезапустить сервер с новыми переменными
uvicorn api.app:app --reload --port 8000

# Получить authorize_url
curl http://localhost:8000/oauth/meetup/login
```

**Ожидаемый ответ:**
```json
{
  "authorize_url": "https://secure.meetup.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Foauth%2Fmeetup%2Fcallback"
}
```

### Шаг 4: Прохождение OAuth флоу
1. **Открыть authorize_url в браузере**
   - Скопировать URL из ответа выше
   - Открыть в браузере

2. **Залогиниться в Meetup**
   - Ввести логин/пароль
   - Разрешить доступ приложению

3. **Получить code**
   - После логина браузер перенаправит на:
   ```
   http://localhost:8000/oauth/meetup/callback?code=YOUR_AUTH_CODE
   ```
   - Скопировать значение `code`

### Шаг 5: Обмен code на токены
```bash
# Выполнить обмен code на токены
curl "http://localhost:8000/oauth/meetup/callback?code=YOUR_AUTH_CODE"
```

**Ожидаемый ответ:**
```json
{
  "ok": true,
  "preview": {
    "access": "abc123…xyz",
    "refresh": "def456…uvw",
    "expires_in": 3600
  },
  "note": "Скопируй ПОЛНЫЕ токены из логов uvicorn и добавь их в .env.local",
  "env_keys": ["MEETUP_ACCESS_TOKEN", "MEETUP_REFRESH_TOKEN"]
}
```

**В логах uvicorn найти:**
```
INFO:     MEETUP_ACCESS_TOKEN=YOUR_FULL_ACCESS_TOKEN
INFO:     MEETUP_REFRESH_TOKEN=YOUR_FULL_REFRESH_TOKEN
```

### Шаг 6: Сохранение токенов
```bash
# Добавить в .env.local:
MEETUP_ACCESS_TOKEN=YOUR_FULL_ACCESS_TOKEN
MEETUP_REFRESH_TOKEN=YOUR_FULL_REFRESH_TOKEN
```

### Шаг 7: Тестирование авторизованных запросов
```bash
# Перезапустить сервер с токенами
uvicorn api.app:app --reload --port 8000

# Протестировать синк Meetup
curl -X POST "http://localhost:8000/events/sources/meetup/sync?lat=-8.6500&lng=115.2160&radius_km=5"
```

**Ожидаемый результат:**
- В логах: `🔐 Используем OAuth авторизацию для Meetup`
- Ответ: `{"inserted": N}` (где N - количество событий)

## 🔍 Проверка безопасности

### ✅ Токены не сохраняются в файлы
- Проверить что в ответе API только маскированное превью
- ПОЛНЫЕ токены только в логах uvicorn

### ✅ Graceful degradation
```bash
# Убрать токены из .env.local
# Протестировать синк
curl -X POST "http://localhost:8000/events/sources/meetup/sync?lat=-8.6500&lng=115.2160&radius_km=5"
# Ожидаем: fallback на API key или пустой список
```

### ✅ Валидация входных данных
```bash
# Невалидные координаты
curl "http://localhost:8000/events/sources/meetup/sync?lat=100&lng=0"
# Ожидаем: 400 Bad Request

# Невалидный радиус
curl "http://localhost:8000/events/sources/meetup/sync?lat=0&lng=0&radius_km=50"
# Ожидаем: 400 Bad Request
```

## 🧪 Автоматические тесты

### Запуск тестов
```bash
# Лёгкий CI (тесты скипаются)
pytest tests/test_oauth_meetup_login.py

# Полный режим (тесты выполняются)
FULL_TESTS=1 pytest tests/test_oauth_meetup_login.py -v
```

### Проверка pre-commit
```bash
pre-commit run --all-files
```

## 🎯 Критерии успеха

### ✅ OAuth флоу работает
- `GET /oauth/meetup/login` возвращает authorize_url
- `GET /oauth/meetup/callback` обменивает code на токены
- Токены логируются в консоль

### ✅ Безопасность соблюдена
- ПОЛНЫЕ токены только в логах
- В ответе API только превью
- Graceful degradation работает

### ✅ Интеграция с источниками
- Источник Meetup использует OAuth токены
- Fallback на API key при отсутствии OAuth
- Никаких ошибок при отсутствии авторизации

### ✅ CI/CD не нарушен
- Лёгкий CI зелёный
- Полный CI зелёный
- Pre-commit проходит

## 🚨 Возможные проблемы

### Проблема: "MEETUP_CLIENT_ID is not configured"
**Решение:** Добавить `MEETUP_CLIENT_ID` в `.env.local`

### Проблема: "Field required" в callback
**Решение:** Передать параметр `code` в URL

### Проблема: "Connection refused" при запуске сервера
**Решение:** Проверить что порт 8000 свободен

### Проблема: "Invalid redirect_uri" в Meetup
**Решение:** Убедиться что redirect_uri в OAuth приложении точно совпадает с настройкой

💖 **OAuth Meetup готов к использованию!** 🔐
