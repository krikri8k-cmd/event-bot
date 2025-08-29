# 🚀 Руководство по применению SQL-миграции через GitHub Actions

## 📋 Задача
Применить скрипт `sql/2025_ics_sources_and_indexes.sql` к прод-базе (Railway) через workflow DB Apply и убедиться, что соединение и миграция работают.

## ✅ Шаг 1: Запуск workflow в GitHub Actions

### 1. Открой GitHub Actions
- Перейди в репозиторий на GitHub
- Нажми на вкладку **Actions**

### 2. Найди workflow "DB Apply"
- В списке workflows найди **"DB Apply (manual)"**
- Нажми на него

### 3. Запусти workflow
- Нажми кнопку **"Run workflow"** (справа)
- В поле **"SQL file path"** оставь значение по умолчанию:
  ```
  sql/2025_ics_sources_and_indexes.sql
  ```
- Нажми **"Run workflow"**

### 4. Следи за выполнением
- Дождись завершения workflow
- Ожидаемые сообщения в логах:
  ```
  Connecting with $DATABASE_URL
  Applying 2025_ics_sources_and_indexes.sql
  CREATE TABLE event_sources ...
  CREATE INDEX ...
  Done.
  ```

## 🔧 Шаг 2: Локальная проверка (опционально)

### Проверка через Python скрипт
```bash
# Установи переменную окружения
export DATABASE_URL="postgresql://USER:PASSWORD@HOST:PORT/DB?sslmode=require"

# Запусти тест подключения
python test_db_connection.py
```

### Проверка через psql (если установлен)
```bash
psql "postgresql://USER:PASSWORD@HOST:PORT/DB?sslmode=require" -c "select current_database();"
```

## 🐛 Траблшутинг

### Частые ошибки:

1. **server does not support SSL / SSL is required**
   - Убедись, что в URL есть `?sslmode=require`
   - Для Railway обычно нужно `require`

2. **could not translate host name**
   - Проверь правильность HOST в DATABASE_URL
   - Убедись, что нет опечаток

3. **password authentication failed**
   - Проверь логин/пароль
   - Возможно, пароль истёк (ротация в Railway)

4. **timeout**
   - Редко на Railway
   - Проверь порт/доступность

## 🔐 Безопасность

Если были утечки/скриншоты с URL:
1. В Railway нажми **Rotate/Regenerate connection string**
2. Обнови секрет `DATABASE_URL` в GitHub → Settings → Secrets and variables → Actions
3. Используй новый URL в формате psql

## ✅ Критерии приёмки

- [ ] Workflow DB Apply завершился **Success**
- [ ] В логах есть строки о применении файла
- [ ] В логах есть подтверждение создания таблиц/индексов
- [ ] (Опционально) psql проверка возвращает имя БД без ошибок

## 📝 Что возвращаем

1. **Ссылку на успешный запуск Actions**
2. **Короткий фрагмент лога** с CREATE TABLE/INDEX или подтверждением «Done»
3. **(Опционально) вывод psql-проверки**

## 🔗 Полезные ссылки

- [GitHub Actions](https://github.com/krikri8k-cmd/event-bot/actions)
- [Railway Dashboard](https://railway.app/dashboard)
- [Workflow файл](.github/workflows/db-apply.yml)
- [SQL миграция](sql/2025_ics_sources_and_indexes.sql)

---

**Примечание**: Предупреждение IDE «Context access might be invalid: DATABASE_URL» можно игнорировать — на рантайме GitHub корректно подставит `${{ secrets.DATABASE_URL }}`.
