"""Толерантное сопоставление slug партнёра: doc_polli == docpolli и т.п.

Проверяем чистые помощники нормализации/канонизации (без БД).
"""

import pytest

from bot_enhanced_v3 import _canonical_partner_key, _normalize_partner_slug

pytestmark = pytest.mark.no_db


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("doc_polli", "docpolli"),
        ("docpolli", "docpolli"),
        ("@doc_polli", "docpolli"),
        ("nastya.mavi", "nastyamavi"),
        ("nastya_mavi", "nastyamavi"),
        ("v.d_fitness", "vdfitness"),
        ("v_d_fitness", "vdfitness"),
        ("Doc-Polli", "docpolli"),
        ("", ""),
        (None, ""),
    ],
)
def test_canonical_partner_key(raw, expected):
    assert _canonical_partner_key(raw) == expected


def test_canonical_key_matches_across_separators():
    """Разные написания одного блогера дают один канонический ключ."""
    assert _canonical_partner_key("doc_polli") == _canonical_partner_key("docpolli")
    assert _canonical_partner_key("nastya.mavi") == _canonical_partner_key("nastya_mavi")
    assert _canonical_partner_key("v.d_fitness") == _canonical_partner_key("v_d_fitness")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("doc_polli", "doc_polli"),
        ("@doc_polli", "doc_polli"),
        ("Nastya.Mavi", "nastya.mavi"),
        ("v.d_fitness", "v.d_fitness"),
        ("doc-polli", "doc-polli"),
    ],
)
def test_normalize_accepts_soft_separators(raw, expected):
    assert _normalize_partner_slug(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        None,
        "a",  # слишком коротко
        "hello world",  # пробел не допускаем (иначе обычные фразы ловились бы как slug)
        "слаг",  # не-латиница
        "x" * 51,  # слишком длинно
    ],
)
def test_normalize_rejects_invalid(raw):
    assert _normalize_partner_slug(raw) is None
