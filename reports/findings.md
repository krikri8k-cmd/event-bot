# 📋 Отчет аудита проекта event-bot

## 🎯 Цель
Аккуратная очистка репозитория от устаревших модулей без регрессий.

## 📊 Общая статистика
- **Всего Python файлов:** ~80
- **Потенциальных сирот:** 32
- **Кандидатов на удаление:** 25
- **Критичных модулей (не трогать):** 15

---

## 🟢 KEEP - Оставить (критичные модули)

### Основные компоненты
- `bot_enhanced_v3.py` - главный файл бота ✅
- `database.py` - модели данных ✅
- `config.py` - конфигурация ✅
- `utils/unified_events_service.py` - основной сервис ✅

### Парсеры (активные)
- `sources/baliforum.py` - парсер BaliForum ✅
- `sources/kudago_source.py` - парсер KudaGo ✅
- `sources/base.py` - базовый класс ✅

### Утилиты (используются)
- `utils/geo_utils.py` - геокодирование ✅
- `utils/simple_timezone.py` - часовые пояса ✅
- `logging_helpers.py` - логирование ✅

---

## 🟡 REFACTOR - Требует рефакторинга

### Дубликаты функционала
- `storage/simple_events_service.py` vs `utils/unified_events_service.py`
  - **Проблема:** Два сервиса для работы с событиями
  - **Решение:** Оставить только `UnifiedEventsService`

### Legacy код в bot_enhanced_v3.py
- Строка 673: "устаревшая функция" `send_detailed_events_list`
- Строка 250: "устаревшая функция" для ссылок  
- Строка 1430: "legacy" клавиатура радиуса

---

## 🔴 DEPRECATE - Кандидаты на удаление

### Одноразовые миграции (безопасно удалить)
- `add_composite_index.py` - применена ✅
- `cleanup_duplicates.py` - выполнена ✅
- `cleanup_old_events_table.py` - выполнена ✅
- `fix_*.py` (5 файлов) - миграции применены ✅
- `migrate_to_simple_architecture.py` - выполнена ✅
- `remove_*_status.py` (3 файла) - миграции применены ✅

### Отладочные скрипты (безопасно удалить)
- `analyze_db_structure.py` - debug ✅
- `bot_health.py` - заменен мониторингом ✅
- `find_yesterday_event.py` - debug ✅
- `smart_ai_generator.py` - заменен `ai_utils.py` ✅

### Неиспользуемые модули
- `storage/region_router.py` - не используется ✅
- `api/ingest/ai_ingest.py` - не используется ✅
- `api/services/user_prefs.py` - не используется ✅
- `utils/port_manager.py` - не используется ✅
- `web/server.py` - не используется ✅

### Замененные файлы
- `deploy.py` - заменен на `.bat/.ps1` скрипты ✅
- `quick_start.py` - заменен на `start_*.bat` ✅

---

## ⚠️ Требует уточнения

### Парсеры (проверить активность)
- `sources/nexudus.py` - используется ли?
- `sources/ics.py` - используется ли?
- `sources/meetup.py` - используется ли?

### Тесты
- Папка `tests/` - нужно проверить актуальность

---

## 🚀 План действий

### Этап 1: Маркировка (безопасно)
1. Добавить DEPRECATED баннеры в файлы-кандидаты
2. Создать `archive/DEPRECATED_READONLY/` 
3. Скопировать кандидатов в архив

### Этап 2: Рефакторинг (осторожно)
1. Убрать дубликаты в `storage/`
2. Очистить legacy код в `bot_enhanced_v3.py`

### Этап 3: Удаление (контролируемо)
1. Удалить только файлы со статусом DEPRECATE
2. Проверить что все тесты проходят
3. Убедиться что бот работает

---

## 🛡️ Критичные модули (НЕ ТРОГАТЬ!)
- `bot_enhanced_v3.py`
- `database.py` 
- `utils/unified_events_service.py`
- `config.py`
- Активные парсеры
- Схема БД и миграции
