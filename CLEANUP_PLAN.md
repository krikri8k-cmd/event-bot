# 🧹 План очистки проекта от ненужных файлов

## 📊 Статистика
- **Всего markdown файлов:** 99
- **Размер проекта:** 411MB
- **Отчетов (*REPORT*.md):** 37 файлов

---

## 🔴 БЕЗОПАСНО УДАЛИТЬ

### 1. Output файлы (5 файлов)
- `add_places_output.txt`
- `check_canggu_output.txt`
- `generate_hints_output.txt`
- `update_names_output.txt`
- `bot_output.txt`

### 2. Одноразовые миграции (применены)
- `add_composite_index.py`
- `apply_029_direct.py`
- `apply_and_save_result.py`
- `apply_migration.bat`
- `apply_rename_migration.py`
- `apply_status_migration.py`
- `apply_sql.py`
- `apply_task_hint_migration.py`
- `apply_total_events_migration.py`
- `check_and_apply_migration.py`
- `do_migration_now.py`

### 3. Одноразовые fix скрипты (выполнены)
- `fix_all_user_events.py`
- `fix_event_coords.py`
- `fix_old_events.py`
- `fix_task_hint.py`
- `fix_user_radius.py`

### 4. Debug/check скрипты (одноразовые проверки)
- `analyze_db_structure.py`
- `bot_health.py`
- `check_bot_status.py`
- `check_canggu_places.py`
- `check_column_simple.py`
- `check_community_starts_at_type.py`
- `check_food_places_details.py`
- `check_git_status.py`
- `check_hints_status.py`
- `check_places_by_category.py`
- `check_task_hint_column.py`

### 5. Тестовые файлы в корне (не в tests/)
- `test_hint_simple.py`
- `quick_test_hint.py`
- `test_output.py`
- `run_kudago_test.py`
- `test_group_router.py`
- `debug_test_router.py`
- `add_test_events.py`

### 6. Устаревшие модули (DEPRECATED)
- `storage/simple_events_service.py` - заменен на `utils/unified_events_service.py`
- `utils/simple_events.py` - не используется
- `utils/community_events_service_old.py` - заменен на `community_events_service.py`
- `utils/port_manager.py` - не используется
- `web/server.py` - не используется (есть `web/health.py`)
- `api/services/user_prefs.py` - не используется

### 7. Замененные файлы
- `deploy.py` - заменен на `.bat/.ps1` скрипты

### 8. SQL файлы в корне (уже применены)
- `add_admin_id_to_events_community.sql`
- `add_chat_id_to_events_user.sql`
- `add_composite_index.sql`
- `check_parser_events.sql`
- `check_user_rockets.sql`
- `create_community_events_table_final.sql`
- `create_tasks_tables.sql`
- `migration_status_management.sql`

---

## 🟡 ПЕРЕМЕСТИТЬ В АРХИВ (отчеты)

### Отчеты о реализации (37 файлов) - можно переместить в `archive/reports/`
- `*_REPORT.md` файлы (37 штук)
- `*_ANALYSIS.md` файлы
- `*_GUIDE.md` файлы (кроме основных README)
- `*_CHECKLIST.md` файлы

**Исключения (оставить):**
- `README.md` - основной файл
- `DEV_GUIDE.md` - может быть полезен
- `SECURITY.md` - важный файл

---

## 🟢 ОСТАВИТЬ (критичные файлы)

### Основные компоненты
- `bot_enhanced_v3.py`
- `database.py`
- `config.py`
- `group_router.py`
- `group_chat_handlers.py`

### Активные сервисы
- `utils/unified_events_service.py`
- `utils/community_events_service.py`
- `tasks_service.py`
- `event_status_manager.py`

### Парсеры
- `sources/*.py` (активные парсеры)

### Миграции
- `migrations/*.sql` - оставить все

### Тесты
- `tests/*.py` - оставить все

### Скрипты
- `scripts/*.py` - проверить индивидуально

---

## 📝 Рекомендации

1. **Сначала переместить в архив**, потом удалить через месяц
2. **Проверить зависимости** перед удалением модулей
3. **Сохранить git историю** - файлы останутся в истории
4. **Создать backup** перед массовым удалением
