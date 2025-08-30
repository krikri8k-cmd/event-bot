import os

import pytest

# Защита от отсутствия fastapi
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

pytestmark = [
    pytest.mark.api,
    pytest.mark.db,
    pytest.mark.skipif(os.getenv("FULL_TESTS") != "1", reason="Full tests disabled"),
]


def test_admin_sources_and_run(api_engine, api_client: TestClient, db_clean):
    # добавим ics-источник
    r = api_client.post(
        "/admin/sources",
        json={
            "type": "ics",
            "url": "https://example.org/calendar.ics",
            "region": "bali",
            "enabled": True,
            "freq_minutes": 1,
        },
    )
    assert r.status_code == 200

    # вручную запустить цикл
    r = api_client.post("/admin/ingest/run")
    assert r.status_code == 200
    # далее можно проверить, что события появились, если настроен мок фетчер. Здесь smoke.
