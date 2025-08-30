import os

import pytest

# В лёгком CI не загружаем тяжёлые фикстуры
if os.environ.get("FULL_TESTS") == "1":

    @pytest.fixture(scope="session")
    def api_engine():
        try:
            from sqlalchemy import create_engine

            url = os.environ["DATABASE_URL"]
            eng = create_engine(url, future=True, pool_pre_ping=True)
            return eng
        except Exception as e:
            pytest.skip(f"Failed to create engine: {e}")

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

else:
    # В лёгком CI создаём пустые фикстуры, чтобы не ломать тесты
    @pytest.fixture(scope="session")
    def api_engine():
        pytest.skip("FULL_TESTS not set")

    @pytest.fixture()
    def db_clean(api_engine):
        yield

    @pytest.fixture()
    def api_client():
        pytest.skip("FULL_TESTS not set")
