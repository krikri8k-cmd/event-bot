# 🔍 Чек-лист для проверки на GitHub

## 🎯 Цель
Убедиться, что все изменения после ревизии проекта корректно отражены на GitHub и проект готов к работе.

---

## 📋 Что нужно проверить

### 1. 🔄 Синхронизация изменений

**Проверить статус git:**
```bash
git status
```

**Должно показать:**
- ✅ Измененные файлы: `utils/geo_utils.py`, `bot_enhanced_v3.py`
- ✅ Удаленные файлы: `utils/geo.py`
- ✅ Новые файлы: `tools/`, `PROJECT_QUALITY_CHECK_TZ.md`, `PROJECT_CLEANUP_REPORT.md`

**Если есть неотслеживаемые файлы:**
```bash
git add .
git commit -m "🧹 Ревизия проекта: убраны дубли, добавлена диагностика

- Объединены utils/geo.py и utils/geo_utils.py
- Добавлена команда /diag_all для диагностики
- Созданы инструменты проверки качества
- Применен единый стиль кода
- Убраны дублирующиеся функции"
```

---

### 2. 📁 Проверка структуры репозитория

**Убедиться, что в репозитории есть:**
- ✅ `tools/` - новые инструменты проверки
- ✅ `PROJECT_QUALITY_CHECK_TZ.md` - ТЗ для проверки качества
- ✅ `PROJECT_CLEANUP_REPORT.md` - отчет о ревизии
- ❌ `utils/geo.py` - должен быть удален

**Проверить, что файлы не в .gitignore:**
```bash
git check-ignore tools/
git check-ignore PROJECT_QUALITY_CHECK_TZ.md
git check-ignore PROJECT_CLEANUP_REPORT.md
```

---

### 3. 🔧 Проверка конфигурации

**Убедиться, что в репозитории НЕТ:**
- ❌ `app.local.env` - файл с секретами
- ❌ `.env` - файл с секретами
- ❌ `event_bot.db` - локальная база данных
- ❌ `venv/` - виртуальное окружение

**Проверить .gitignore:**
```bash
cat .gitignore
```

**Должно содержать:**
```
# Environment files
.env
.env.local
app.local.env
*.env

# Database
*.db
*.sqlite

# Virtual environment
venv/
env/

# Python cache
__pycache__/
*.pyc
*.pyo

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
```

---

### 4. 📝 Проверка документации

**Убедиться, что обновлен README.md:**
- ✅ Описание новых инструментов в `tools/`
- ✅ Инструкции по запуску проверок качества
- ✅ Команда `/diag_all` в списке доступных команд

**Проверить, что есть:**
- ✅ `PROJECT_QUALITY_CHECK_TZ.md` - для Cursor-агентов
- ✅ `PROJECT_CLEANUP_REPORT.md` - отчет о проделанной работе
- ✅ `tools/README.md` - документация инструментов

---

### 5. 🧪 Проверка тестов

**Убедиться, что тесты проходят:**
```bash
# Локально
python -m pytest tests/ -v

# Или через GitHub Actions (если настроены)
```

**Проверить, что нет сломанных импортов:**
```bash
python -c "from utils.geo_utils import haversine_km; print('✅ Импорт работает')"
python -c "from api.services.events import get_events_nearby; print('✅ Импорт работает')"
```

---

### 6. 🚀 Проверка развертывания

**Если используется Railway/Heroku:**
- ✅ Переменные окружения настроены
- ✅ `DATABASE_URL` указывает на продакшн БД
- ✅ `TELEGRAM_TOKEN` настроен
- ✅ `WEBHOOK_URL` корректный

**Проверить health check:**
```bash
curl https://your-app.up.railway.app/health
```

---

### 7. 📊 Проверка производительности

**Убедиться, что:**
- ✅ Время парсинга ≤ 30 секунд
- ✅ Геокодирование кэшируется
- ✅ База данных оптимизирована
- ✅ Индексы созданы

---

### 8. 🔍 Проверка безопасности

**Убедиться, что:**
- ❌ Секреты не попали в код
- ❌ API ключи не в репозитории
- ✅ Все пароли в переменных окружения
- ✅ .gitignore правильно настроен

---

## 🚨 Критические проверки

### ❌ НЕ ДОЛЖНО БЫТЬ В РЕПОЗИТОРИИ:
```
app.local.env
.env
event_bot.db
venv/
__pycache__/
*.pyc
```

### ✅ ДОЛЖНО БЫТЬ В РЕПОЗИТОРИИ:
```
tools/
PROJECT_QUALITY_CHECK_TZ.md
PROJECT_CLEANUP_REPORT.md
utils/geo_utils.py (обновленный)
bot_enhanced_v3.py (с /diag_all)
```

---

## 🔧 Команды для проверки

### Проверка статуса:
```bash
git status
git log --oneline -5
```

### Проверка изменений:
```bash
git diff HEAD~1
git show --name-only HEAD
```

### Проверка файлов:
```bash
ls -la tools/
ls -la utils/
```

### Проверка .gitignore:
```bash
git check-ignore app.local.env
git check-ignore venv/
git check-ignore *.db
```

---

## 📝 Чек-лист для выполнения

- [ ] Проверить `git status`
- [ ] Добавить новые файлы в git
- [ ] Убедиться, что секреты не в репозитории
- [ ] Проверить .gitignore
- [ ] Обновить README.md
- [ ] Запустить тесты
- [ ] Проверить импорты
- [ ] Проверить развертывание
- [ ] Сделать commit и push
- [ ] Проверить на GitHub

---

## 🎯 Ожидаемый результат

После проверки на GitHub должно быть:
- ✅ Все изменения синхронизированы
- ✅ Секреты не попали в репозиторий
- ✅ Документация обновлена
- ✅ Тесты проходят
- ✅ Проект готов к работе

---

**Готово к проверке!** 🚀
