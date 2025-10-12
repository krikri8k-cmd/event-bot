from __future__ import annotations

import sys
from pathlib import Path

# tomllib есть в стандартной библиотеке Python 3.12+
try:
    import tomllib  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    tomllib = None


ROOT = Path(__file__).resolve().parents[1]


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def test_python_version_is_313_or_higher():
    assert sys.version_info >= (3, 13), f"Python is {sys.version}"


def test_env_template_uses_psycopg2_scheme():
    """Проверяем, что пример DSN в env-шаблоне — psycopg2."""
    content = read_text(ROOT / "env.local.template")
    assert "postgresql+psycopg2://" in content, "Expected psycopg2 DSN in env.local.template"


def test_no_psycopg_v3_dsn_in_repo():
    """В репозитории не должно быть postgresql+psycopg:// (v3 диалект)."""
    bad_hits = []
    for p in ROOT.rglob("*.py"):
        # Исключаем тестовые файлы и виртуальное окружение
        if "tests" in str(p) or "venv" in str(p) or "site-packages" in str(p):
            continue
        text = read_text(p)
        # Ищем только реальное использование psycopg v3, а не код для его замены
        if "postgresql+psycopg://" in text and "replace" not in text:
            bad_hits.append(str(p))
    assert not bad_hits, f"Found psycopg v3 DSN usage in: {bad_hits}"


def test_pyproject_has_target_py312_and_requires_312():
    """Проверяем ruff target-version = py312 и requires-python >= 3.12."""
    pj = ROOT / "pyproject.toml"
    assert pj.exists(), "pyproject.toml is missing"

    if tomllib:
        data = tomllib.loads(read_text(pj))
        # requires-python
        req = (data.get("project") or {}).get("requires-python") or ""
        assert ">=3.12" in req, f"requires-python must be >=3.12, got: {req!r}"
        # ruff target-version
        ruff = (data.get("tool") or {}).get("ruff") or {}
        target = ruff.get("target-version") or ""
        assert target in {"py312", "py3.12"}, f"unexpected ruff target-version: {target!r}"
    else:
        # fallback: грубая проверка по тексту
        text = read_text(pj)
        assert ">=3.12" in text
        assert "target-version" in text and "py312" in text
