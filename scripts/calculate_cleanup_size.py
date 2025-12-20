#!/usr/bin/env python3
"""Подсчет размера файлов для удаления"""

import sys
from pathlib import Path

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

FILES_TO_DELETE = [
    "add_places_output.txt",
    "check_canggu_output.txt",
    "generate_hints_output.txt",
    "update_names_output.txt",
    "bot_output.txt",
    "add_composite_index.py",
    "apply_029_direct.py",
    "apply_and_save_result.py",
    "apply_migration.bat",
    "apply_rename_migration.py",
    "apply_status_migration.py",
    "apply_sql.py",
    "apply_task_hint_migration.py",
    "apply_total_events_migration.py",
    "check_and_apply_migration.py",
    "do_migration_now.py",
    "fix_all_user_events.py",
    "fix_event_coords.py",
    "fix_old_events.py",
    "fix_task_hint.py",
    "fix_user_radius.py",
    "analyze_db_structure.py",
    "bot_health.py",
    "check_bot_status.py",
    "check_canggu_places.py",
    "check_column_simple.py",
    "check_community_starts_at_type.py",
    "check_food_places_details.py",
    "check_git_status.py",
    "check_hints_status.py",
    "check_places_by_category.py",
    "check_task_hint_column.py",
    "test_hint_simple.py",
    "quick_test_hint.py",
    "test_output.py",
    "run_kudago_test.py",
    "test_group_router.py",
    "debug_test_router.py",
    "add_test_events.py",
    "storage/simple_events_service.py",
    "utils/simple_events.py",
    "utils/community_events_service_old.py",
    "utils/port_manager.py",
    "web/server.py",
    "api/services/user_prefs.py",
    "deploy.py",
    "add_admin_id_to_events_community.sql",
    "add_chat_id_to_events_user.sql",
    "add_composite_index.sql",
    "check_parser_events.sql",
    "check_user_rockets.sql",
    "create_community_events_table_final.sql",
    "create_tasks_tables.sql",
    "migration_status_management.sql",
]

EXCEPTIONS = ["README.md", "DEV_GUIDE.md", "SECURITY.md", "CLEANUP_PLAN.md"]
REPORT_PATTERNS = ["*_REPORT.md", "*_ANALYSIS.md", "*_GUIDE.md", "*_CHECKLIST.md"]

total_size = 0
found_files = 0
not_found = []

print("=" * 60)
print("ПОДСЧЕТ РАЗМЕРА ФАЙЛОВ ДЛЯ УДАЛЕНИЯ")
print("=" * 60)

for file_path in FILES_TO_DELETE:
    full_path = Path(file_path)
    if full_path.exists():
        size = full_path.stat().st_size
        total_size += size
        found_files += 1
        print(f"{file_path}: {size/1024:.1f} KB")
    else:
        not_found.append(file_path)

print(f"\n{'=' * 60}")
print(f"Найдено файлов: {found_files}")
print(f"Не найдено: {len(not_found)}")
print(f"Общий размер: {total_size/1024:.1f} KB ({total_size/1024/1024:.2f} MB)")

# Подсчет отчетов
print(f"\n{'=' * 60}")
print("ПОДСЧЕТ ОТЧЕТОВ ДЛЯ АРХИВАЦИИ")
print("=" * 60)

report_size = 0
report_count = 0

for pattern in REPORT_PATTERNS:
    for file_path in Path(".").glob(pattern):
        if file_path.name not in EXCEPTIONS:
            size = file_path.stat().st_size
            report_size += size
            report_count += 1

print(f"Найдено отчетов: {report_count}")
print(f"Общий размер отчетов: {report_size/1024:.1f} KB ({report_size/1024/1024:.2f} MB)")

print(f"\n{'=' * 60}")
print("ИТОГО")
print("=" * 60)
total_all = total_size + report_size
print(f"Всего будет освобождено: {total_all/1024:.1f} KB ({total_all/1024/1024:.2f} MB)")
print(f"  - Удаление файлов: {total_size/1024:.1f} KB")
print(f"  - Архивация отчетов: {report_size/1024:.1f} KB")
