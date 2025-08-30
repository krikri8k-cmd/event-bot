# 🪟 Руководство по тестированию для Windows PowerShell

## 🔧 Настройка переменной окружения

### В PowerShell:
```powershell
$env:DATABASE_URL = "postgresql://USER:PASSWORD@HOST:PORT/DB?sslmode=require"
```

### Для постоянного хранения (создай файл .env.local):
```powershell
# Создай файл .env.local в корне проекта
echo "DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DB?sslmode=require" > .env.local
```

## 🚀 Команды для тестирования

### 1. Тест подключения к БД
```powershell
# Вариант 1: Через PowerShell скрипт
.\scripts\test_db.ps1

# Вариант 2: Напрямую через Python
python test_db_connection.py
```

### 2. Тест миграции
```powershell
# Вариант 1: Через PowerShell скрипт
.\scripts\test_migration.ps1

# Вариант 2: Напрямую через Python
python test_migration.py
```

### 3. Применение миграции
```powershell
# Вариант 1: Через PowerShell скрипт
.\scripts\apply_migration.ps1

# Вариант 2: Напрямую через Python
python scripts\apply_sql.py sql\2025_ics_sources_and_indexes.sql
```

## 🔧 Альтернативные варианты

### Установка Make для Windows
```powershell
# Через Chocolatey (если установлен)
choco install make

# Или через winget
winget install GnuWin32.Make

# После установки можно использовать:
make test-db
make test-migration
```

### Использование WSL (Windows Subsystem for Linux)
```bash
# В WSL терминале
export DATABASE_URL="postgresql://USER:PASSWORD@HOST:PORT/DB?sslmode=require"
make test-db
make test-migration
```

## 📋 Полный пример работы

```powershell
# 1. Установи переменную окружения
$env:DATABASE_URL = "postgresql://USER:PASSWORD@HOST:PORT/DB?sslmode=require"

# 2. Тест подключения
.\scripts\test_db.ps1

# 3. Тест миграции
.\scripts\test_migration.ps1

# 4. Применение миграции (если тесты прошли)
.\scripts\apply_migration.ps1
```

## 🐛 Траблшутинг

### Ошибка "execution policy"
```powershell
# Разреши выполнение скриптов
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Ошибка "python не найден"
```powershell
# Убедись, что Python в PATH
python --version

# Или используй полный путь
C:\Users\YourName\AppData\Local\Programs\Python\Python313\python.exe test_db_connection.py
```

### Ошибка "psycopg2 не найден"
```powershell
# Установи зависимости
pip install -r requirements.txt
```

## ✅ Ожидаемый результат

При успешном выполнении увидишь:
```
🔗 Подключаюсь к БД...
✅ Подключение успешно!
   База данных: your_database_name
   Пользователь: your_username
   PostgreSQL версия: PostgreSQL 15.x
📋 Существующие таблицы: events, event_sources, ...
```

---

**Примечание**: Все PowerShell скрипты находятся в папке `scripts/` и имеют расширение `.ps1`
