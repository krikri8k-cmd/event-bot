#!/usr/bin/env python3
"""
Проверяет и исправляет проблему с frozen полями:
1. Проверяет, применена ли миграция 035
2. Проверяет, раскомментированы ли поля в database.py
3. Проверяет, используются ли frozen данные в коде
"""

import os
import sys
from pathlib import Path

# Устанавливаем UTF-8 для вывода в Windows
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from sqlalchemy import text

from database import get_session, init_engine

# Загружаем переменные окружения
env_path = Path(__file__).parent.parent / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)

# Инициализируем базу данных
db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("[ERROR] DATABASE_URL not found in environment variables")
    sys.exit(1)

print("=" * 60)
print("CHECKING FROZEN TASKS SYSTEM")
print("=" * 60)
print()

# Инициализируем подключение к БД
try:
    init_engine(db_url)
    print("[OK] Database connection initialized")
except Exception as e:
    print(f"[ERROR] Failed to initialize database: {e}")
    sys.exit(1)

print()

# 1. Check if migration is applied
print("1. CHECK: Is migration 035 applied?")
print("-" * 60)

with get_session() as session:
    try:
        result = session.execute(
            text(
                """
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'user_tasks' 
                AND column_name LIKE 'frozen%'
                ORDER BY column_name;
                """
            )
        )
        columns = result.fetchall()

        if len(columns) == 4:
            print("[OK] Migration 035 applied - found 4 columns:")
            for col_name, col_type in columns:
                print(f"   - {col_name} ({col_type})")
            migration_applied = True
        else:
            print(f"[ERROR] Migration 035 NOT applied - found {len(columns)} columns instead of 4")
            if columns:
                print("   Found columns:")
                for col_name, col_type in columns:
                    print(f"   - {col_name} ({col_type})")
            else:
                print("   frozen_* columns are missing in DB")
            migration_applied = False
    except Exception as e:
        print(f"[ERROR] Error checking migration: {e}")
        migration_applied = False

print()

# 2. Check if fields are uncommented in database.py
print("2. CHECK: Are frozen fields uncommented in database.py?")
print("-" * 60)

database_py = Path(__file__).parent.parent / "database.py"
if database_py.exists():
    content = database_py.read_text(encoding="utf-8")

    # Check if fields are commented
    if "# frozen_title:" in content:
        print("[ERROR] frozen_* fields are COMMENTED in database.py")
        print("   Need to uncomment lines 99-102")
        fields_commented = True
    elif "frozen_title: Mapped" in content:
        print("[OK] frozen_* fields are uncommented in database.py")
        fields_commented = False
    else:
        print("[WARN] Could not determine field status in database.py")
        fields_commented = True
else:
    print("[ERROR] database.py file not found")
    fields_commented = True

print()

# 3. Check if frozen data exists in existing tasks
print("3. CHECK: Do frozen data exist in existing tasks?")
print("-" * 60)

if migration_applied:
    with get_session() as session:
        try:
            result = session.execute(
                text(
                    """
                    SELECT 
                        COUNT(*) as total,
                        COUNT(frozen_title) as with_frozen_title,
                        COUNT(frozen_description) as with_frozen_description
                    FROM user_tasks
                    WHERE status = 'active';
                    """
                )
            )
            stats = result.fetchone()

            total = stats[0]
            with_title = stats[1]
            with_desc = stats[2]

            print("Statistics of active tasks:")
            print(f"   - Total: {total}")
            print(f"   - With frozen_title: {with_title}")
            print(f"   - With frozen_description: {with_desc}")

            if total > 0:
                percentage = (with_title / total * 100) if total > 0 else 0
                print(f"   - Percentage with frozen data: {percentage:.1f}%")

                if percentage < 50:
                    print()
                    print("[WARN] Less than 50% of tasks have frozen data")
                    print("   -> Recommended to run migration script:")
                    print("   -> python scripts/migrate_old_tasks_to_frozen.py")
        except Exception as e:
            print(f"[ERROR] Error checking data: {e}")
else:
    print("[WARN] Skipped (migration not applied)")

print()

# 4. Final recommendations
print("=" * 60)
print("RECOMMENDATIONS")
print("=" * 60)
print()

if not migration_applied:
    print("[ACTION] STEP 1: Apply migration 035")
    print("   Run one of:")
    print("   1. railway run psql $DATABASE_URL < migrations/035_add_frozen_fields_to_user_tasks.sql")
    print("   2. python scripts/apply_sql.py migrations/035_add_frozen_fields_to_user_tasks.sql")
    print("   3. psql $DATABASE_URL -f migrations/035_add_frozen_fields_to_user_tasks.sql")
    print()

if fields_commented:
    print("[ACTION] STEP 2: Uncomment fields in database.py")
    print("   Open database.py, lines 99-102")
    print("   Remove # symbols before:")
    print("   - frozen_title: Mapped[str | None] = ...")
    print("   - frozen_description: Mapped[str | None] = ...")
    print("   - frozen_task_hint: Mapped[str | None] = ...")
    print("   - frozen_category: Mapped[str | None] = ...")
    print()

if migration_applied and not fields_commented:
    print("[OK] STEP 3: Run migration for old tasks (optional)")
    print("   python scripts/migrate_old_tasks_to_frozen.py")
    print()
    print("[OK] STEP 4: Restart bot")
    print()

if migration_applied and not fields_commented:
    print("=" * 60)
    print("[SUCCESS] ALL CHECKS PASSED - SYSTEM READY")
    print("=" * 60)
else:
    print("=" * 60)
    print("[WARN] ACTION REQUIRED - SEE RECOMMENDATIONS ABOVE")
    print("=" * 60)
