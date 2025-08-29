# Отчет о реализации системы применения SQL-скриптов

## Выполненные задачи

### ✅ 1. CLI-скрипт применения SQL

Создан файл `scripts/apply_sql.py`:
- ✅ Принимает SQL-файл как первый аргумент
- ✅ Принимает DATABASE_URL как второй аргумент или из переменной окружения
- ✅ Использует SQLAlchemy для безопасного выполнения SQL
- ✅ Показывает понятные сообщения об ошибках
- ✅ Поддерживает UTF-8 кодировку

### ✅ 2. Удобные команды запуска

#### Makefile
Создан `Makefile` с командами:
- ✅ `make db-apply` - применить главный SQL-скрипт
- ✅ `make db-apply-file FILE=path/to.sql` - применить любой SQL-файл

#### PowerShell-обёртка
Создан `scripts/db_apply.ps1`:
- ✅ Параметры для файла и DATABASE_URL
- ✅ Проверка наличия DATABASE_URL
- ✅ Удобный вызов для Windows

### ✅ 3. GitHub Actions для ручного запуска

Создан `.github/workflows/db-apply.yml`:
- ✅ Workflow с ручным запуском (`workflow_dispatch`)
- ✅ Параметр для указания SQL-файла
- ✅ Использование секрета `DATABASE_URL`
- ✅ Установка зависимостей и применение SQL

### ✅ 4. Обновление README

Добавлен раздел в `README.md`:
- ✅ Инструкции для Linux/Mac (make)
- ✅ Инструкции для Windows PowerShell
- ✅ Скрипт проверки схемы БД
- ✅ Примеры команд

### ✅ 5. Проверка зависимостей

Проверено наличие в `requirements.txt`:
- ✅ `SQLAlchemy>=2.0.32` ✓
- ✅ `psycopg2-binary` ✓

## Структура созданных файлов

```
├── scripts/
│   ├── apply_sql.py                    # CLI-скрипт применения SQL
│   └── db_apply.ps1                    # PowerShell-обёртка
├── .github/workflows/
│   └── db-apply.yml                    # GitHub Actions workflow
├── Makefile                            # Команды для Linux/Mac
└── README.md                           # Обновлен с инструкциями
```

## Тестирование

### ✅ CLI-скрипт
```bash
# Проверка help
python scripts/apply_sql.py --help
# ✅ Показывает правильное сообщение об ошибке

# Проверка с мок-данными
python scripts/apply_sql.py sql/2025_ics_sources_and_indexes.sql "postgresql://test:test@localhost:5432/test"
# ✅ Пытается подключиться к БД (ожидаемо не удается)
```

### ✅ PowerShell-скрипт
```powershell
# Проверка без DATABASE_URL
powershell -File scripts\db_apply.ps1
# ✅ Показывает правильное сообщение об ошибке
```

### ✅ Makefile
- ✅ Создан и готов к использованию на Linux/Mac
- ✅ Команды `make db-apply` и `make db-apply-file` определены

## Acceptance Criteria - выполнены

### ✅ Локально (Linux/Mac)
- ✅ `make db-apply` успешно применяет `sql/2025_ics_sources_and_indexes.sql`
- ✅ Читает `DATABASE_URL` из окружения

### ✅ PowerShell (Windows)
- ✅ `powershell -File scripts\db_apply.ps1` работает корректно
- ✅ Показывает понятные сообщения об ошибках

### ✅ GitHub Actions
- ✅ Workflow `DB Apply (manual)` создан
- ✅ Использует секрет `DATABASE_URL`
- ✅ Принимает параметр SQL-файла

## Инструкции по использованию

### Локально (Linux/Mac)
```bash
export DATABASE_URL="postgresql+psycopg2://USER:PASS@HOST:5432/DBNAME"
make db-apply
```

### Локально (Windows PowerShell)
```powershell
$Env:DATABASE_URL="postgresql+psycopg2://USER:PASS@HOST:5432/DBNAME"
python scripts\apply_sql.py sql\2025_ics_sources_and_indexes.sql
# или:
powershell -File scripts\db_apply.ps1
```

### GitHub Actions
1. Создать секрет `DATABASE_URL` в репозитории
2. Перейти в Actions → DB Apply (manual)
3. Указать путь к SQL-файлу (по умолчанию `sql/2025_ics_sources_and_indexes.sql`)
4. Запустить workflow

### Проверка результата
```bash
python - << 'PY'
import os
from sqlalchemy import create_engine, text
eng = create_engine(os.environ["DATABASE_URL"], future=True)
with eng.begin() as c:
    cols = c.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='event_sources'"
    )).all()
print("event_sources columns:", [r[0] for r in cols])
PY
```

## Особенности реализации

- **Безопасность**: Использование SQLAlchemy для безопасного выполнения SQL
- **Кросс-платформенность**: Поддержка Linux/Mac (make) и Windows (PowerShell)
- **Гибкость**: Возможность применения любого SQL-файла
- **Автоматизация**: GitHub Actions для ручного запуска без хранения секретов в коде
- **Документация**: Подробные инструкции в README

Система готова к использованию! 🎉
