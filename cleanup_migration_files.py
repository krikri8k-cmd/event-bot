#!/usr/bin/env python3
"""
Скрипт для очистки временных файлов миграции
"""

import os


def main():
    print("🧹 Очистка временных файлов миграции")
    print("=" * 50)

    # Список временных файлов для удаления
    temp_files = [
        # Временные скрипты миграции
        "check_events_structure.py",
        "check_migration_complete.py",
        "complete_migration.py",
        "fix_migration.py",
        "test_unified_service.py",
        "test_bot_functionality.py",
        "cleanup_migration_files.py",
        # Старые скрипты миграции (если есть)
        "migrate_events_tables.py",
        "MIGRATION_GUIDE.md",
        # Backup файлы (если есть)
        "events_parser_backup.sql",
        "events_user_backup.sql",
    ]

    # Файлы для сохранения (важные)
    keep_files = [
        # Основные файлы миграции
        "migrations/merge_events_tables_production.sql",
        "migrations/safe_cleanup_old_tables.sql",
        "migrate_events_production.py",
        "cleanup_old_events_tables.py",
        "run_production_migration.sh",
        "run_production_migration.ps1",
        "PRODUCTION_MIGRATION_GUIDE.md",
        # Откат
        "migrations/rollback_merge_events.sql",
        "migrations/pre_migration_check.sql",
    ]

    print("📋 Файлы для удаления:")
    deleted_count = 0
    not_found_count = 0

    for file_path in temp_files:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"  ✅ Удален: {file_path}")
                deleted_count += 1
            except Exception as e:
                print(f"  ❌ Ошибка удаления {file_path}: {e}")
        else:
            print(f"  ℹ️ Не найден: {file_path}")
            not_found_count += 1

    print("\n📊 Результат очистки:")
    print(f"  Удалено файлов: {deleted_count}")
    print(f"  Не найдено: {not_found_count}")

    print("\n💾 Сохранены важные файлы:")
    for file_path in keep_files:
        if os.path.exists(file_path):
            print(f"  ✅ {file_path}")
        else:
            print(f"  ❓ {file_path} (не найден)")

    print("\n🎉 Очистка завершена!")
    print("💡 Важные файлы миграции сохранены для будущего использования")


if __name__ == "__main__":
    main()
