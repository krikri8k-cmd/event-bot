# scripts/apply_sql.py
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine

# Загружаем переменные окружения
env_path = Path(__file__).parent.parent / "app.local.env"
if env_path.exists():
    load_dotenv(env_path)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/apply_sql.py <sql_file> [DATABASE_URL]")
        sys.exit(1)

    sql_file = sys.argv[1]
    db_url = sys.argv[2] if len(sys.argv) >= 3 else os.environ.get("DATABASE_URL")
    if not db_url:
        print("Error: Provide DATABASE_URL env or as 2nd argument.")
        sys.exit(2)

    with open(sql_file, encoding="utf-8") as f:
        sql = f.read()

    engine = create_engine(db_url, future=True, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)

    print(f"Applied: {sql_file} -> {db_url}")


if __name__ == "__main__":
    main()
