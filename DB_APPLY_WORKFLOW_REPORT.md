# 🎯 Отчёт о выполнении ТЗ: DB Apply Workflow

## ✅ Выполненные задачи

### 1. Обновлён файл workflow
**Путь**: `.github/workflows/db-apply.yml`

**Изменения**:
- ✅ Переименован параметр `sql_file` → `sql_path`
- ✅ Добавлены `permissions: contents: read`
- ✅ Заменён Python/SQLAlchemy подход на psql
- ✅ Добавлена установка `postgresql-client`
- ✅ Добавлена логика для автоматического добавления `sslmode=require`
- ✅ Добавлена проверка наличия секрета `DATABASE_URL`
- ✅ Используется `-v ON_ERROR_STOP=1` для остановки при ошибках

### 2. Добавлен раздел в README
**Файл**: `README.md`

**Добавлено**:
- ✅ Раздел "🗄️ DB Apply (manual)" в конец файла
- ✅ Пошаговые инструкции по запуску workflow
- ✅ Важное примечание о секрете `DATABASE_URL`

### 3. Проверка SQL файла
**Файл**: `sql/2025_ics_sources_and_indexes.sql`

- ✅ Файл существует и содержит валидный SQL
- ✅ Создаёт таблицу `event_sources`
- ✅ Создаёт необходимые индексы
- ✅ Добавляет поля в таблицу `events`

## 🔧 Технические детали

### Workflow структура:
```yaml
name: DB Apply (manual)
on:
  workflow_dispatch:
    inputs:
      sql_path:
        description: 'Path to SQL file to apply'
        required: true
        default: 'sql/2025_ics_sources_and_indexes.sql'

permissions:
  contents: read

jobs:
  apply:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
      - name: Install psql client
      - name: Apply SQL using psql
```

### Логика обработки DATABASE_URL:
```bash
# Проверка наличия секрета
if [[ -z "$RAW_DB_URL" ]]; then
  echo "DATABASE_URL secret is not set"; exit 1
fi

# Автоматическое добавление sslmode=require для Railway
DB_URL="$RAW_DB_URL"
if [[ "$DB_URL" != *"sslmode="* ]]; then
  if [[ "$DB_URL" == *"?"* ]]; then
    DB_URL="${DB_URL}&sslmode=require"
  else
    DB_URL="${DB_URL}?sslmode=require"
  fi
fi
```

## 📋 Ожидаемое поведение

### При запуске workflow:
1. **Checkout** - клонирование репозитория
2. **Install psql client** - установка PostgreSQL клиента
3. **Apply SQL using psql** - применение SQL файла

### Ожидаемые логи:
```
Applying sql/2025_ics_sources_and_indexes.sql ...
CREATE TABLE event_sources ...
CREATE INDEX ix_event_sources_enabled ...
CREATE INDEX ix_event_sources_region ...
CREATE INDEX ix_event_sources_next ...
ALTER TABLE events ADD COLUMN source ...
CREATE INDEX ix_events_source ...
...
Done.
```

## 🔐 Безопасность

- ✅ Используется секрет `DATABASE_URL` из GitHub Secrets
- ✅ Добавлены `permissions: contents: read` для ограничения доступа
- ✅ Workflow запускается только вручную (`workflow_dispatch`)
- ✅ SSL режим принудительно включается для Railway

## 🚀 Готовность к деплою

### Требования:
- ✅ Секрет `DATABASE_URL` должен быть добавлен в `Settings → Secrets and variables → Actions`
- ✅ Формат: `postgresql://user:pass@host:port/db` или `postgresql+psycopg2://user:pass@host:port/db`

### Тестирование:
1. Создать ветку `chore/db-apply-workflow`
2. Запушить изменения
3. Создать PR
4. Проверить появление workflow в Actions
5. Запустить workflow вручную для тестирования

## 📝 Commit message

```
chore(ci): add manual DB Apply workflow (psql)

- Replace Python/SQLAlchemy approach with direct psql client
- Add automatic sslmode=require for Railway compatibility
- Add DATABASE_URL secret validation
- Update README with workflow usage instructions
- Add proper error handling with ON_ERROR_STOP=1
```

---

**Статус**: 🟢 ТЗ выполнено полностью

Все требования из технического задания реализованы. Workflow готов к использованию.
