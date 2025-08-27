import os

import pytest

# В лёгком CI не загружаем тяжёлые фикстуры
if os.environ.get("FULL_TESTS") == "1":
    try:
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine, text

        from api.app import app  # локальный импорт отделён пустой строкой

        @pytest.fixture(scope="session")
        def api_engine():
            url = os.environ["DATABASE_URL"]
            eng = create_engine(url, future=True, pool_pre_ping=True)
            yield eng
            eng.dispose()

        @pytest.fixture()
        def db_clean(api_engine):
            # Чистим табличку перед каждым тестом
            with api_engine.begin() as c:
                c.execute(text("DELETE FROM events"))
            yield

        @pytest.fixture()
        def api_client():
            return TestClient(app)

    except ImportError:
        # Если пакеты не установлены, создаём пустые фикстуры
        @pytest.fixture(scope="session")
        def api_engine():
            pytest.skip("sqlalchemy not available")

        @pytest.fixture()
        def db_clean(api_engine):
            yield

        @pytest.fixture()
        def api_client():
            pytest.skip("fastapi not available")
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
