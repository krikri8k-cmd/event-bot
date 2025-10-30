import os
import sys

from sqlalchemy import create_engine, text

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def load_env():
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.local.env"))
    if load_dotenv and os.path.exists(env_path):
        load_dotenv(env_path)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/apply_migration.py <path-to-sql>")
        sys.exit(1)

    sql_path = sys.argv[1]
    if not os.path.exists(sql_path):
        print(f"❌ File not found: {sql_path}")
        sys.exit(1)

    load_env()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL is not set. Ensure app.local.env is configured.")
        sys.exit(1)

    engine = create_engine(db_url, future=True)

    with open(sql_path, encoding="utf-8") as f:
        sql = f.read()

    # Split on semicolons; keep simple for our migrations
    raw_statements = [s.strip() for s in sql.split(";") if s.strip()]
    # Отфильтруем блоки, состоящие только из комментариев
    statements = []
    for s in raw_statements:
        body = "\n".join(line for line in s.splitlines() if not line.strip().startswith("--")).strip()
        if body:
            statements.append(body)
    print(f"Applying {len(statements)} statements from {sql_path}...")
    with engine.begin() as conn:
        for idx, stmt in enumerate(statements, 1):
            print(f"  [{idx}/{len(statements)}] Executing...")
            conn.execute(text(stmt))
    print("✅ Migration applied")


if __name__ == "__main__":
    main()
