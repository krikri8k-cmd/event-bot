import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

env_path = Path(__file__).parent / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)

db_url = os.getenv("DATABASE_URL")
if not db_url:
    sys.exit(1)

engine = create_engine(db_url, future=True)

with engine.connect() as conn:
    result = conn.execute(
        text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'task_places' AND column_name = 'task_hint'
    """)
    )
    exists = result.fetchone()
    print("EXISTS" if exists else "NOT_EXISTS")
