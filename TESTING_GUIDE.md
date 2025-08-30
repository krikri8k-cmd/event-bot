# 🧪 Руководство по тестированию Event Bot

## 📋 Шпаргалка для работы

### Импорт datetime
```python
import datetime as dt
# Используй dt.timezone.utc для работы с UTC
now = dt.datetime.now(dt.timezone.utc)
```

### Маркеры тестов
- **API тесты**: `pytest -m api`
- **DB тесты**: `pytest -m db`  
- **API или DB тесты**: `pytest -m "api or db"`

### Режимы CI

#### 🚀 Полный режим (FULL_TESTS=1)
```bash
# Установи переменную окружения
export FULL_TESTS=1  # Linux/Mac
$env:FULL_TESTS="1"  # PowerShell

# Запусти все API/DB тесты
pytest -m "api or db"
```

#### ⚡ Лёгкий CI (по умолчанию)
```bash
# Без FULL_TESTS API/DB тесты автоматически пропускаются
pytest -m "api or db"  # Результат: 0 selected, все тесты deselected/skipped
```

## 📁 Структура тестов

### Маркеры в файлах
```python
# API тесты
pytestmark = pytest.mark.api

# DB тесты  
pytestmark = pytest.mark.db
```

### Условное выполнение
```python
# В лёгком CI пропускаем модуль целиком
if os.environ.get("FULL_TESTS") != "1":
    pytest.skip("Skipping API tests in light CI", allow_module_level=True)
```

## 🎯 Примеры использования

### 1. Создание API теста
```python
import datetime as dt
import pytest

pytestmark = pytest.mark.api

if os.environ.get("FULL_TESTS") != "1":
    pytest.skip("Skipping API tests in light CI", allow_module_level=True)

def test_api_endpoint(api_client):
    # Используем datetime с timezone
    now = dt.datetime.now(dt.timezone.utc)
    # ... тест
```

### 2. Создание DB теста
```python
import datetime as dt
import pytest

pytestmark = pytest.mark.db

if os.environ.get("FULL_TESTS") != "1":
    pytest.skip("Skipping DB tests in light CI", allow_module_level=True)

def test_db_operation(api_engine, db_clean):
    # Используем datetime с timezone
    event_time = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)
    # ... тест
```

## 🔧 Настройка в pyproject.toml

```toml
[tool.pytest.ini_options]
markers = [
    "api: API-тесты, требуют FastAPI и БД",
    "db: DB-smoke без FastAPI",
    "timeout: marks tests with timeout",
]
```

## 🚀 Быстрый старт

1. **Установи зависимости**: `pip install -e ".[dev]"`
2. **Лёгкий CI**: `pytest -m "api or db"` (тесты пропускаются)
3. **Полный режим**: `FULL_TESTS=1 pytest -m "api or db"` (тесты запускаются)

## 💡 Советы

- Всегда используй `import datetime as dt` и `dt.timezone.utc`
- Маркируй тесты как `api` или `db` в зависимости от типа
- В лёгком CI тесты автоматически пропускаются для экономии времени
- Для локальной разработки используй `FULL_TESTS=1`
