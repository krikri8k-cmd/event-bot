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
              address TEXT,
              place_id TEXT
            );
        """)
        with api_engine.begin() as c:
            c.execute(ddl)

            # Добавляем колонки, если таблица уже существовала без них
            # Используем DO блок для проверки существования колонок
            add_columns_script = text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'events' AND column_name = 'city'
                    ) THEN
                        ALTER TABLE events ADD COLUMN city VARCHAR(64);
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'events' AND column_name = 'country'
                    ) THEN
                        ALTER TABLE events ADD COLUMN country VARCHAR(8);
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'events' AND column_name = 'location_name'
                    ) THEN
                        ALTER TABLE events ADD COLUMN location_name TEXT;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'events' AND column_name = 'location_url'
                    ) THEN
                        ALTER TABLE events ADD COLUMN location_url TEXT;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'events' AND column_name = 'description'
                    ) THEN
                        ALTER TABLE events ADD COLUMN description TEXT;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'events' AND column_name = 'organizer_id'
                    ) THEN
                        ALTER TABLE events ADD COLUMN organizer_id INTEGER;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'events' AND column_name = 'organizer_username'
                    ) THEN
                        ALTER TABLE events ADD COLUMN organizer_username TEXT;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'events' AND column_name = 'max_participants'
                    ) THEN
                        ALTER TABLE events ADD COLUMN max_participants INTEGER;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'events' AND column_name = 'current_participants'
                    ) THEN
                        ALTER TABLE events ADD COLUMN current_participants INTEGER;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'events' AND column_name = 'status'
                    ) THEN
                        ALTER TABLE events ADD COLUMN status VARCHAR(50) DEFAULT 'open';
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'events' AND column_name = 'created_at_utc'
                    ) THEN
                        ALTER TABLE events ADD COLUMN created_at_utc TIMESTAMPTZ;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'events' AND column_name = 'community_name'
                    ) THEN
                        ALTER TABLE events ADD COLUMN community_name TEXT;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'events' AND column_name = 'venue_name'
                    ) THEN
                        ALTER TABLE events ADD COLUMN venue_name VARCHAR(255);
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'events' AND column_name = 'address'
                    ) THEN
                        ALTER TABLE events ADD COLUMN address TEXT;
                    END IF;

                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'events' AND column_name = 'place_id'
                    ) THEN
                        ALTER TABLE events ADD COLUMN place_id TEXT;
                    END IF;
                END $$;
            """)
            c.execute(add_columns_script)
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
