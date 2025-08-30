# 🎯 Отчёт о готовности к применению SQL-миграции

## ✅ Проверено и готово

### 1. Workflow файл
- ✅ `.github/workflows/db-apply.yml` существует и настроен
- ✅ Использует правильный путь к скрипту: `scripts/apply_sql.py`
- ✅ Принимает параметр `sql_file` с дефолтным значением
- ✅ Использует секрет `DATABASE_URL`

### 2. SQL миграция
- ✅ `sql/2025_ics_sources_and_indexes.sql` существует
- ✅ Содержит создание таблицы `event_sources`
- ✅ Содержит создание индексов
- ✅ Содержит добавление полей в таблицу `events`

### 3. Скрипт применения
- ✅ `scripts/apply_sql.py` существует и работает
- ✅ Использует SQLAlchemy для подключения
- ✅ Читает SQL файл и применяет его
- ✅ Обрабатывает ошибки

### 4. Зависимости
- ✅ `requirements.txt` содержит `SQLAlchemy` и `psycopg2-binary`
- ✅ Workflow устанавливает зависимости

### 5. Тестовые скрипты
- ✅ `test_db_connection.py` - для проверки подключения
- ✅ `test_migration.py` - для тестирования миграции
- ✅ Обновлён `Makefile` с новыми командами

## 🚀 Инструкции для выполнения

### Шаг 1: Запуск GitHub Actions
1. Открой [GitHub Actions](https://github.com/krikri8k-cmd/event-bot/actions)
2. Найди workflow **"DB Apply (manual)"**
3. Нажми **"Run workflow"**
4. Оставь значение по умолчанию: `sql/2025_ics_sources_and_indexes.sql`
5. Нажми **"Run workflow"**

### Шаг 2: Локальная проверка (опционально)
```bash
# Тест подключения
make test-db

# Тест миграции
make test-migration
```

## 📋 Что ожидается в логах

```
Connecting with $DATABASE_URL
Applying 2025_ics_sources_and_indexes.sql
CREATE TABLE event_sources ...
CREATE INDEX ix_event_sources_enabled ...
CREATE INDEX ix_event_sources_region ...
CREATE INDEX ix_event_sources_next ...
ALTER TABLE events ADD COLUMN source ...
CREATE INDEX ix_events_source ...
...
Done.
```

## 🔧 Команды для тестирования

```bash
# Установи переменную окружения
export DATABASE_URL="postgresql://USER:PASSWORD@HOST:PORT/DB?sslmode=require"

# Тест подключения
make test-db

# Тест миграции
make test-migration

# Применение миграции
make db-apply
```

## 🐛 Возможные проблемы

1. **SSL ошибки** - убедись, что в URL есть `?sslmode=require`
2. **Аутентификация** - проверь логин/пароль в Railway
3. **Хост недоступен** - проверь правильность HOST в DATABASE_URL

## 📝 Критерии успеха

- [ ] Workflow завершился с **Success**
- [ ] В логах есть подтверждение создания таблиц/индексов
- [ ] Таблица `event_sources` создана в БД
- [ ] Индексы созданы корректно

---

**Статус**: 🟢 Готово к выполнению

Все файлы проверены и настроены. Можно приступать к запуску workflow в GitHub Actions.
