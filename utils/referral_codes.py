"""Утилиты для работы с реферальными кодами партнёров"""

from typing import Any

from sqlalchemy import text

from database import get_engine


def get_referral_code_for_url(source_url: str) -> tuple[str | None, str]:
    """
    Получает реферальный код для URL источника

    Args:
        source_url: URL источника (ICS календарь, API и т.д.)

    Returns:
        Tuple (referral_code, referral_param) или (None, 'ref') если не найден
    """
    if not source_url:
        return None, "ref"

    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                SELECT referral_code, referral_param
                FROM partner_referral_codes
                WHERE lower(source_url) = lower(:url)
                  AND is_active = TRUE
                LIMIT 1
            """),
            {"url": source_url},
        )
        row = result.fetchone()
        if row:
            return row[0], row[1] or "ref"

    return None, "ref"


def add_partner_referral(
    source_url: str,
    referral_code: str,
    referral_param: str = "ref",
    partner_name: str | None = None,
) -> int:
    """
    Добавляет или обновляет реферальный код для партнёра

    Args:
        source_url: URL источника
        referral_code: Реферальный код
        referral_param: Название параметра (по умолчанию: 'ref')
        partner_name: Название партнёра (опционально)

    Returns:
        ID записи
    """
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO partner_referral_codes (
                    source_url, referral_code, referral_param, partner_name, is_active
                ) VALUES (
                    :source_url, :referral_code, :referral_param, :partner_name, TRUE
                )
                ON CONFLICT (lower(source_url))
                DO UPDATE SET
                    referral_code = EXCLUDED.referral_code,
                    referral_param = EXCLUDED.referral_param,
                    partner_name = COALESCE(EXCLUDED.partner_name, partner_referral_codes.partner_name),
                    updated_at = NOW()
                RETURNING id
            """),
            {
                "source_url": source_url,
                "referral_code": referral_code,
                "referral_param": referral_param,
                "partner_name": partner_name,
            },
        )
        return result.fetchone()[0]


def list_partner_referrals() -> list[dict[str, Any]]:
    """Возвращает список всех партнёрских реферальных кодов"""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                SELECT id, source_url, referral_code, referral_param, partner_name, is_active, created_at
                FROM partner_referral_codes
                ORDER BY created_at DESC
            """)
        )
        return [dict(row._mapping) for row in result]
