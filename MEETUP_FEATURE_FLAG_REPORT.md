# Отчет: Фиче-флаг для интеграции Meetup

## Статус: ✅ ЗАВЕРШЕНО

### Что было реализовано

1. **Создан api/config.py** с фиче-флагами
   - `MEETUP_ENABLED=0` по умолчанию (выключено)
   - `MEETUP_MOCK=0` по умолчанию
   - Опциональные OAuth параметры

2. **Обновлен .env.local.template**
   - Добавлен блок Meetup с комментариями
   - Все параметры Meetup закомментированы по умолчанию

3. **Обновлен api/app.py**
   - Условное подключение Meetup роутов через `if settings.MEETUP_ENABLED`
   - OAuth колбэк и sync эндпоинт доступны только при включенном флаге
   - Сохранен мок-режим внутри колбэка

4. **Обновлены тесты Meetup**
   - Все тесты помечены маркером `pytest.mark.meetup`
   - Условный skip при `MEETUP_ENABLED != "1"`
   - Обновлены все файлы: `test_oauth_meetup_*.py`

5. **Обновлен pyproject.toml**
   - Добавлен маркер `meetup: tests that require Meetup enabled`

6. **Обновлен README.md**
   - Добавлен раздел "Meetup (фиче-флаг)"
   - Инструкции по включению интеграции

### Ключевые особенности реализации

#### В `api/config.py`:
```python
# Фиче-флаг Meetup (ВЫКЛ по умолчанию)
MEETUP_ENABLED = os.getenv("MEETUP_ENABLED", "0") == "1"

# Мок-режим оставляем как есть
MEETUP_MOCK = os.getenv("MEETUP_MOCK", "0") == "1"

# Опциональная OAuth-конфигурация (не обязательна при выключенном флаге)
MEETUP_CLIENT_ID = os.getenv("MEETUP_CLIENT_ID")
MEETUP_CLIENT_SECRET = os.getenv("MEETUP_CLIENT_SECRET")
MEETUP_REDIRECT_URI = os.getenv("MEETUP_REDIRECT_URI", "http://localhost:8000/oauth/meetup/callback")
```

#### В `api/app.py`:
```python
# Meetup OAuth роутер (только если включен)
if settings.MEETUP_ENABLED:
    oauth_router = APIRouter(prefix="/oauth/meetup", tags=["oauth"])
    
    @oauth_router.get("/callback")
    async def meetup_callback(...):
        # Мок-режим для локалки/тестов
        if settings.MEETUP_MOCK:
            return {"ok": True, "code": code, "state": state, "mock": True}
        # Боевой путь: обмен кода на токены
        ...

    # Подключаем OAuth роутер
    app.include_router(oauth_router)

# Meetup sync endpoint (только если включен)
if settings.MEETUP_ENABLED:
    @app.post("/events/sources/meetup/sync")
    async def sync_meetup(...):
        ...
```

#### В тестах:
```python
pytestmark = [
    pytest.mark.api,
    pytest.mark.meetup,
    pytest.mark.skipif(os.getenv("MEETUP_ENABLED") != "1", reason="Meetup disabled"),
]
```

### Acceptance Criteria - Проверка

#### ✅ По умолчанию (`MEETUP_ENABLED=0`):
- **`GET /oauth/meetup/callback` возвращает `404 Not Found`**: ✅ Проверено
- **Все meetup-тесты skipped**: ✅ Проверено

#### ✅ При включении (`MEETUP_ENABLED=1`):
- **`GET /oauth/meetup/callback?code=test123&state=xyz` работает**: ✅ Проверено
- **Мок-режим `MEETUP_MOCK=1` возвращает `{"ok": true, "mock": true, ...}`**: ✅ Проверено
- **Боевой режим пытается обменять code на токены**: ✅ Проверено

### Тестирование

#### Ручное тестирование:
```bash
# По умолчанию (выключено)
uvicorn api.app:app --reload --port 8000
curl "http://localhost:8000/oauth/meetup/callback?code=test123&state=xyz"
# Ответ: {"detail":"Not Found"} (404)

# Включено с мок-режимом
export MEETUP_ENABLED=1
export MEETUP_MOCK=1
uvicorn api.app:app --reload --port 8000
curl "http://localhost:8000/oauth/meetup/callback?code=test123&state=xyz"
# Ответ: {"ok":true,"code":"test123","state":"xyz","mock":true}
```

#### Автоматические тесты:
```bash
# Без MEETUP_ENABLED - все тесты skipped
pytest tests/test_oauth_meetup_*.py
# Результат: все тесты SKIPPED (Meetup disabled)

# С MEETUP_ENABLED=1 - тесты запускаются
export MEETUP_ENABLED=1
pytest tests/test_oauth_meetup_*.py
# Результат: тесты выполняются (если нет проблем с БД)
```

### Результат

✅ **Задача выполнена полностью:**

1. **Фиче-флаг реализован** - `MEETUP_ENABLED=0` по умолчанию
2. **Эндпоинты условно подключены** - доступны только при включенном флаге
3. **Мок-режим сохранен** - работает внутри колбэка при `MEETUP_MOCK=1`
4. **Тесты условно запускаются** - пропускаются при выключенном флаге
5. **Документация обновлена** - инструкции по включению интеграции
6. **Конфигурация улучшена** - централизованное управление флагами

### Использование

#### Включить интеграцию Meetup:
```bash
# .env.local
MEETUP_ENABLED=1
MEETUP_CLIENT_ID=your_client_id
MEETUP_CLIENT_SECRET=your_client_secret
```

#### Для тестирования (мок-режим):
```bash
# .env.local
MEETUP_ENABLED=1
MEETUP_MOCK=1
```

#### По умолчанию:
- Все эндпоинты `/oauth/meetup/*` недоступны (404)
- Все тесты Meetup пропускаются
- CI остается зеленым

Интеграция Meetup теперь полностью контролируется фиче-флагом и по умолчанию выключена! 🎉
