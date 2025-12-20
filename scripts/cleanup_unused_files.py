#!/usr/bin/env python3
"""
Скрипт для безопасного удаления ненужных файлов из проекта
"""

import shutil
import sys
from pathlib import Path

# Устанавливаем UTF-8 для Windows
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Файлы для удаления (безопасно)
FILES_TO_DELETE = [
    # Output файлы
    "add_places_output.txt",
    "check_canggu_output.txt",
    "generate_hints_output.txt",
    "update_names_output.txt",
    "bot_output.txt",
    # Одноразовые миграции
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
    # Одноразовые fix скрипты
    "fix_all_user_events.py",
    "fix_event_coords.py",
    "fix_old_events.py",
    "fix_task_hint.py",
    "fix_user_radius.py",
    # Debug/check скрипты
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
    # Тестовые файлы в корне
    "test_hint_simple.py",
    "quick_test_hint.py",
    "test_output.py",
    "run_kudago_test.py",
    "test_group_router.py",
    "debug_test_router.py",
    "add_test_events.py",
    # Устаревшие модули
    "storage/simple_events_service.py",
    "utils/simple_events.py",
    "utils/community_events_service_old.py",
    "utils/port_manager.py",
    "web/server.py",
    "api/services/user_prefs.py",
    # Замененные файлы
    "deploy.py",
    # SQL файлы в корне (уже применены)
    "add_admin_id_to_events_community.sql",
    "add_chat_id_to_events_user.sql",
    "add_composite_index.sql",
    "check_parser_events.sql",
    "check_user_rockets.sql",
    "create_community_events_table_final.sql",
    "create_tasks_tables.sql",
    "migration_status_management.sql",
]

# Файлы для перемещения в архив (отчеты)
REPORTS_TO_ARCHIVE = [
    # Отчеты о реализации
    "*_REPORT.md",
    "*_ANALYSIS.md",
    "*_GUIDE.md",
    "*_CHECKLIST.md",
]

# Исключения (не удалять)
EXCEPTIONS = [
    "README.md",
    "DEV_GUIDE.md",
    "SECURITY.md",
    "CLEANUP_PLAN.md",
]


def delete_files(dry_run=True):
    """Удаляет ненужные файлы"""
    deleted = []
    not_found = []

    for file_path in FILES_TO_DELETE:
        full_path = Path(file_path)
        if full_path.exists():
            if dry_run:
                print(f"🗑️  [DRY RUN] Удалил бы: {file_path}")
            else:
                try:
                    full_path.unlink()
                    print(f"✅ Удален: {file_path}")
                    deleted.append(file_path)
                except Exception as e:
                    print(f"❌ Ошибка при удалении {file_path}: {e}")
        else:
            not_found.append(file_path)

    if not_found:
        print(f"\n⚠️  Не найдено {len(not_found)} файлов (возможно, уже удалены)")

    return deleted


def archive_reports(dry_run=True):
    """Перемещает отчеты в архив"""
    archive_dir = Path("archive/reports")

    if not archive_dir.exists():
        if not dry_run:
            archive_dir.mkdir(parents=True, exist_ok=True)
            print(f"📁 Создана папка: {archive_dir}")
        else:
            print(f"📁 [DRY RUN] Создал бы папку: {archive_dir}")

    archived = []
    patterns = ["*_REPORT.md", "*_ANALYSIS.md", "*_GUIDE.md", "*_CHECKLIST.md"]

    for pattern in patterns:
        for file_path in Path(".").glob(pattern):
            if file_path.name not in EXCEPTIONS:
                dest = archive_dir / file_path.name
                if dry_run:
                    print(f"📦 [DRY RUN] Переместил бы: {file_path.name} -> archive/reports/")
                else:
                    try:
                        shutil.move(str(file_path), str(dest))
                        print(f"📦 Перемещен: {file_path.name}")
                        archived.append(file_path.name)
                    except Exception as e:
                        print(f"❌ Ошибка при перемещении {file_path.name}: {e}")

    return archived


if __name__ == "__main__":
    import sys

    dry_run = "--execute" not in sys.argv
    auto_yes = "--yes" in sys.argv

    if dry_run:
        print("🔍 РЕЖИМ ПРОВЕРКИ (dry run) - файлы не будут удалены")
        print("Для реального удаления запустите: python scripts/cleanup_unused_files.py --execute\n")
    else:
        print("⚠️  РЕЖИМ УДАЛЕНИЯ - файлы будут удалены!")
        if not auto_yes:
            response = input("Продолжить? (yes/no): ")
            if response.lower() != "yes":
                print("Отменено")
                sys.exit(0)
        else:
            print("✅ Автоматическое подтверждение (--yes)")
        print()

    print("=" * 60)
    print("1. Удаление ненужных файлов")
    print("=" * 60)
    deleted = delete_files(dry_run=dry_run)

    print(f"\n{'=' * 60}")
    print("2. Перемещение отчетов в архив")
    print("=" * 60)
    archived = archive_reports(dry_run=dry_run)

    print(f"\n{'=' * 60}")
    print("РЕЗУЛЬТАТЫ")
    print("=" * 60)
    print(f"✅ Удалено файлов: {len(deleted)}")
    print(f"📦 Перемещено отчетов: {len(archived)}")

    if dry_run:
        print("\n💡 Для реального удаления запустите:")
        print("   python scripts/cleanup_unused_files.py --execute")
