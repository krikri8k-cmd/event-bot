#!/usr/bin/env python3
"""
Простые тесты для CI без внешних зависимостей
"""

import os

import pytest

# В лёгком CI (по умолчанию) пропускаем тест целиком.
if os.environ.get("FULL_TESTS") != "1":
    pytest.skip("Skipping heavy tests in light CI", allow_module_level=True)


def test_placeholder():
    # здесь могут быть тяжёлые интеграционные проверки,
    # которые запускаем только при FULL_TESTS=1
    assert True
