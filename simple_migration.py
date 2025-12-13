import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Загружаем env
env_path = Path(__file__).parent / "app.local.env"
load_dotenv(env_path)

db_url = os.getenv("DATABASE_URL")
print(f"DB URL: {db_url[:50] if db_url else 'NOT FOUND'}...")

if not db_url:
    print("ERROR: No DATABASE_URL")
    exit(1)

engine = create_engine(db_url, future=True)

# Проверяем столбец
with engine.connect() as conn:
    result = conn.execute(
        text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'task_places' AND column_name = 'task_hint'
    """)
    )
    exists = result.fetchone()
    print(f"Column exists before: {exists is not None}")

# Применяем миграцию
if not exists:
    print("Applying migration...")
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE task_places ADD COLUMN IF NOT EXISTS task_hint VARCHAR(200)"))
        conn.execute(text("COMMENT ON COLUMN task_places.task_hint IS 'Короткое задание/подсказка'"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_task_places_task_hint_null "
                "ON task_places(category, place_type) WHERE task_hint IS NULL"
            )
        )
    print("Migration applied!")

# Проверяем снова
with engine.connect() as conn:
    result = conn.execute(
        text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'task_places' AND column_name = 'task_hint'
    """)
    )
    exists_after = result.fetchone()
    print(f"Column exists after: {exists_after is not None}")

if exists_after:
    print("SUCCESS: Column task_hint created!")
else:
    print("ERROR: Column still not found")
