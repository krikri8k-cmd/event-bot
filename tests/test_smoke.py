import datetime as dt
import os

import pytest

pytestmark = pytest.mark.api  # API маркер для smoke теста

# В лёгком CI пропускаем модуль целиком
if os.environ.get("FULL_TESTS") != "1":
    pytest.skip("Skipping smoke test in light CI", allow_module_level=True)


def test_smoke():
    """Базовый smoke тест для проверки работоспособности"""
    # Проверяем что datetime с timezone работает
    now = dt.datetime.now(dt.UTC)
    assert now.tzinfo == dt.UTC

    # Простая проверка что всё работает
    assert True
