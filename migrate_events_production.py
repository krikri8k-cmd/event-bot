#!/usr/bin/env python3
"""
ПРОДАКШЕН миграция: объединение events_parser и events_user в events
Включает: дедуп-ключи, CONCURRENTLY индексы, нормализацию TZ/гео, батч-миграцию, безопасный cleanup
"""

import argparse
import sys
import time
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine, text

from config import load_settings


class ProductionMigration:
    """Класс для продакшен миграции с проверками и безопасностью"""

    def __init__(self, dry_run: bool = False, force: bool = False):
        self.dry_run = dry_run
        self.force = force
        self.engine = None
        self.stats = {}

    def connect(self) -> bool:
        """Подключение к базе данных"""
        try:
            settings = load_settings()
            self.engine = create_engine(settings.database_url)

            # Проверяем подключение
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            print("✅ Подключение к базе данных установлено")
            return True
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            return False

    def check_prerequisites(self) -> bool:
        """Проверка предварительных условий"""
        print("🔍 Проверка предварительных условий...")

        with self.engine.connect() as conn:
            # Проверяем существование таблиц
            result = conn.execute(
                text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN ('events', 'events_parser', 'events_user')
            """)
            )

            existing_tables = {row[0] for row in result.fetchall()}

            if "events" not in existing_tables:
                print("❌ Таблица events не существует!")
                return False

            if "events_parser" not in existing_tables and "events_user" not in existing_tables:
                print("ℹ️ Таблицы events_parser и events_user не существуют - миграция не нужна")
                return False

            # Проверяем размер таблиц
            for table in ["events", "events_parser", "events_user"]:
                if table in existing_tables:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.fetchone()[0]
                    self.stats[f"{table}_count"] = count
                    print(f"📊 {table}: {count:,} записей")

            # Проверяем активные соединения
            result = conn.execute(
                text("""
                SELECT count(*) as active_connections
                FROM pg_stat_activity
                WHERE state = 'active' AND datname = current_database()
            """)
            )
            active_connections = result.fetchone()[0]

            if active_connections > 10 and not self.force:
                print(f"⚠️ Много активных соединений ({active_connections}). Используйте --force для продолжения")
                return False

            print(f"📡 Активных соединений: {active_connections}")

        return True

    def run_pre_migration_check(self) -> bool:
        """Выполняет предварительную проверку"""
        print("🔍 Выполняем предварительную проверку...")

        try:
            with open("migrations/pre_migration_check.sql", encoding="utf-8") as f:
                sql_content = f.read()

            with self.engine.connect() as conn:
                # Выполняем SQL по блокам
                for block in sql_content.split(";"):
                    block = block.strip()
                    if block and not block.startswith("--"):
                        try:
                            result = conn.execute(text(block))
                            # Выводим результаты проверки
                            if result.returns_rows:
                                rows = result.fetchall()
                                for row in rows:
                                    if isinstance(row, tuple) and len(row) > 1:
                                        print(f"  {row[0]}: {row[1]}")
                                    else:
                                        print(f"  {row[0]}")
                        except Exception as e:
                            print(f"⚠️ Предупреждение в проверке: {e}")

            return True
        except Exception as e:
            print(f"❌ Ошибка предварительной проверки: {e}")
            return False

    def run_migration(self) -> bool:
        """Выполняет основную миграцию"""
        if self.dry_run:
            print("🧪 DRY RUN: Миграция не будет выполнена")
            return True

        print("🚀 Начинаем продакшен миграцию...")

        try:
            # Выполняем основную миграцию
            with open("migrations/merge_events_tables_production.sql", encoding="utf-8") as f:
                sql_content = f.read()

            with self.engine.connect() as conn:
                # Разделяем на блоки для лучшего контроля
                blocks = sql_content.split("COMMIT;")

                for i, block in enumerate(blocks):
                    block = block.strip()
                    if not block:
                        continue

                    print(f"📦 Выполняем блок {i+1}/{len(blocks)}...")

                    # Выполняем блок
                    for statement in block.split(";"):
                        statement = statement.strip()
                        if statement and not statement.startswith("--"):
                            try:
                                conn.execute(text(statement))
                                conn.commit()
                            except Exception as e:
                                print(f"⚠️ Ошибка в блоке {i+1}: {e}")
                                print(f"Statement: {statement[:100]}...")
                                return False

                    # Небольшая пауза между блоками
                    time.sleep(0.5)

            print("✅ Миграция выполнена успешно")
            return True

        except Exception as e:
            print(f"❌ Ошибка миграции: {e}")
            return False

    def verify_migration(self) -> bool:
        """Проверяет результат миграции"""
        print("🔍 Проверяем результат миграции...")

        try:
            with self.engine.connect() as conn:
                # Проверяем общую статистику
                result = conn.execute(
                    text("""
                    SELECT
                        source,
                        COUNT(*) as count,
                        MIN(created_at_utc) as earliest,
                        MAX(created_at_utc) as latest
                    FROM events
                    WHERE source IS NOT NULL
                    GROUP BY source
                    ORDER BY count DESC
                """)
                )

                print("📊 События по источникам:")
                total_migrated = 0
                for row in result.fetchall():
                    source, count, earliest, latest = row
                    print(f"  {source}: {count:,} событий ({earliest} - {latest})")
                    total_migrated += count

                # Проверяем дубликаты
                result = conn.execute(
                    text("""
                    SELECT COUNT(*) as duplicates FROM (
                        SELECT source, external_id, COUNT(*) as cnt
                        FROM events
                        WHERE source IS NOT NULL AND external_id IS NOT NULL
                        GROUP BY source, external_id
                        HAVING COUNT(*) > 1
                    ) dup_check
                """)
                )

                duplicates = result.fetchone()[0]
                if duplicates > 0:
                    print(f"⚠️ Найдено дубликатов: {duplicates}")
                else:
                    print("✅ Дубликатов не найдено")

                # Проверяем нормализацию
                result = conn.execute(
                    text("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(geo_hash) as with_geo_hash,
                        COUNT(starts_at_normalized) as with_normalized_time
                    FROM events
                """)
                )

                total, with_geo, with_time = result.fetchone()
                print(
                    f"📊 Нормализация: {with_geo:,}/{total:,} с geo_hash, "
                    f"{with_time:,}/{total:,} с нормализованным временем"
                )

                # Проверяем индексы
                result = conn.execute(
                    text("""
                    SELECT indexname
                    FROM pg_indexes
                    WHERE tablename = 'events'
                    AND indexname LIKE 'idx_events_%'
                    ORDER BY indexname
                """)
                )

                indexes = [row[0] for row in result.fetchall()]
                print(f"📊 Создано индексов: {len(indexes)}")

                return True

        except Exception as e:
            print(f"❌ Ошибка проверки: {e}")
            return False

    def run_safe_cleanup(self) -> bool:
        """Выполняет безопасный cleanup"""
        print("🗑️ Выполняем безопасный cleanup...")

        if self.dry_run:
            print("🧪 DRY RUN: Cleanup не будет выполнен")
            return True

        try:
            with open("migrations/safe_cleanup_old_tables.sql", encoding="utf-8") as f:
                sql_content = f.read()

            with self.engine.connect() as conn:
                # Выполняем cleanup
                for block in sql_content.split(";"):
                    block = block.strip()
                    if block and not block.startswith("--"):
                        try:
                            result = conn.execute(text(block))
                            conn.commit()

                            # Выводим результаты
                            if result.returns_rows:
                                rows = result.fetchall()
                                for row in rows:
                                    print(f"  {row[0]}")
                        except Exception as e:
                            print(f"⚠️ Ошибка в cleanup: {e}")
                            return False

            print("✅ Cleanup выполнен успешно")
            return True

        except Exception as e:
            print(f"❌ Ошибка cleanup: {e}")
            return False

    def run_full_migration(self) -> bool:
        """Выполняет полную миграцию"""
        print("🔄 ПРОДАКШЕН МИГРАЦИЯ: объединение таблиц событий")
        print("=" * 60)

        # Этап 1: Подключение
        if not self.connect():
            return False

        # Этап 2: Проверка предварительных условий
        if not self.check_prerequisites():
            return False

        # Этап 3: Предварительная проверка
        if not self.run_pre_migration_check():
            return False

        # Этап 4: Подтверждение
        if not self.dry_run:
            print("\n⚠️ ВНИМАНИЕ: Эта операция изменит структуру базы данных!")
            print("Рекомендуется создать резервную копию перед продолжением.")

            if not self.force:
                response = input("\nПродолжить миграцию? (yes/no): ").strip().lower()
                if response not in ["yes", "y", "да", "д"]:
                    print("❌ Миграция отменена пользователем")
                    return False

        # Этап 5: Миграция
        if not self.run_migration():
            return False

        # Этап 6: Проверка
        if not self.verify_migration():
            return False

        # Этап 7: Cleanup (опционально)
        if not self.dry_run:
            cleanup_response = input("\nВыполнить cleanup старых таблиц? (yes/no): ").strip().lower()
            if cleanup_response in ["yes", "y", "да", "д"]:
                if not self.run_safe_cleanup():
                    print("⚠️ Cleanup не удался, но миграция завершена")

        print("\n🎉 МИГРАЦИЯ ЗАВЕРШЕНА УСПЕШНО!")
        return True


def main():
    parser = argparse.ArgumentParser(description="Продакшен миграция таблиц событий")
    parser.add_argument("--dry-run", action="store_true", help="Только проверки, без изменений")
    parser.add_argument("--force", action="store_true", help="Продолжить без подтверждений")
    parser.add_argument("--check-only", action="store_true", help="Только проверки")

    args = parser.parse_args()

    migration = ProductionMigration(dry_run=args.dry_run, force=args.force)

    if args.check_only:
        # Только проверки
        if migration.connect() and migration.check_prerequisites():
            migration.run_pre_migration_check()
            migration.verify_migration()
        return 0

    # Полная миграция
    success = migration.run_full_migration()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
