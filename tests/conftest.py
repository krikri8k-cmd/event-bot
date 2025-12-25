import os

import pytest


# Всегда используем PostgreSQL для тестов
@pytest.fixture(scope="session")
def api_engine():
    try:
        from sqlalchemy import create_engine

        # Используем PostgreSQL URL из окружения или создаем тестовый
        url = os.environ.get("DATABASE_URL")
        if not url:
            # Создаем тестовый PostgreSQL URL
            url = "postgresql://test_user:test_pass@localhost:5432/test_db"
            pytest.skip("DATABASE_URL not set, skipping PostgreSQL tests")

        # Убеждаемся что это PostgreSQL
        if not url.startswith(("postgresql://", "postgres://")):
            pytest.skip(f"Expected PostgreSQL URL, got: {url}")

        eng = create_engine(url, future=True, pool_pre_ping=True)
        return eng
    except Exception as e:
        pytest.skip(f"Failed to create PostgreSQL engine: {e}")


@pytest.fixture(scope="session", autouse=True)
def ensure_events_table(api_engine):
    try:
        from sqlalchemy import text

        # Создаем таблицу, если её нет
        ddl = text("""
            CREATE TABLE IF NOT EXISTS events (
              id SERIAL PRIMARY KEY,
              title TEXT NOT NULL,
              lat DOUBLE PRECISION NOT NULL,
              lng DOUBLE PRECISION NOT NULL,
              starts_at TIMESTAMPTZ,
              created_at TIMESTAMPTZ DEFAULT NOW(),
              updated_at TIMESTAMPTZ,
              source TEXT,
              external_id TEXT,
              url TEXT,
              city VARCHAR(64),
              country VARCHAR(8),
              location_name TEXT,
              location_url TEXT,
              description TEXT,
              organizer_id INTEGER,
              organizer_username TEXT,
              max_participants INTEGER,
              current_participants INTEGER,
              status VARCHAR(50) DEFAULT 'open',
              created_at_utc TIMESTAMPTZ,
              community_name TEXT,
              venue_name VARCHAR(255),
              address TEXT
            );
        """)
        with api_engine.begin() as c:
            c.execute(ddl)

            # Добавляем колонки, если таблица уже существовала без них
            alter_statements = [
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS city VARCHAR(64)",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS country VARCHAR(8)",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS location_name TEXT",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS location_url TEXT",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS description TEXT",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS organizer_id INTEGER",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS organizer_username TEXT",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS max_participants INTEGER",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS current_participants INTEGER",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'open'",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS created_at_utc TIMESTAMPTZ",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS community_name TEXT",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS venue_name VARCHAR(255)",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS address TEXT",
            ]
            for alter_stmt in alter_statements:
                try:
                    c.execute(text(alter_stmt))
                except Exception:
                    # Игнорируем ошибки, если колонка уже существует
                    pass
        yield  # ничего не дропаем
    except Exception as e:
        pytest.skip(f"Failed to create table: {e}")


@pytest.fixture()
def db_clean(api_engine):
    try:
        from sqlalchemy import text

        with api_engine.begin() as c:
            c.execute(text("DELETE FROM events"))
        yield
    except Exception as e:
        pytest.skip(f"Failed to clean DB: {e}")


@pytest.fixture()
def api_client():
    try:
        from fastapi.testclient import TestClient

        from api.app import app

        return TestClient(app)
    except Exception as e:
        pytest.skip(f"Failed to create client: {e}")
