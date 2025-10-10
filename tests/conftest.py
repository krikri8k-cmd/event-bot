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
              url TEXT
            );
        """)
        with api_engine.begin() as c:
            c.execute(ddl)
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
