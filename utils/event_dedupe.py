"""Cross-source deduplication for parser events (title + time + location)."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Connection

_STOP_TITLE_TOKENS = frozenset(
    {
        "the",
        "and",
        "в",
        "на",
        "и",
        "at",
        "in",
        "bali",
        "event",
        "событие",
        "fest",
        "festival",
        "фестиваль",
    }
)


def normalize_event_title(title: str) -> str:
    text = unicodedata.normalize("NFKD", title or "")
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _title_fingerprint(title: str) -> str:
    tokens = [t for t in normalize_event_title(title).split() if len(t) >= 3 and t not in _STOP_TITLE_TOKENS]
    if len(tokens) >= 2:
        return " ".join(tokens[:2])
    if tokens:
        return tokens[0]
    return normalize_event_title(title)[:40]


def titles_likely_same(left: str, right: str) -> bool:
    left_tokens = {t for t in normalize_event_title(left).split() if len(t) >= 3 and t not in _STOP_TITLE_TOKENS}
    right_tokens = {t for t in normalize_event_title(right).split() if len(t) >= 3 and t not in _STOP_TITLE_TOKENS}
    if not left_tokens or not right_tokens:
        return _title_fingerprint(left) == _title_fingerprint(right)
    overlap = left_tokens & right_tokens
    min_size = min(len(left_tokens), len(right_tokens))
    return len(overlap) >= max(2, min_size)


def _time_bucket(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC).replace(second=0, microsecond=0)
    minute = (dt.minute // 30) * 30
    return dt.replace(minute=minute).isoformat()


def compute_dedupe_key(
    title: str,
    starts_at: datetime,
    lat: float | None,
    lng: float | None,
    city: str | None = None,
) -> str:
    title_fp = _title_fingerprint(title)
    time_part = _time_bucket(starts_at)
    lat_part = f"{float(lat):.3f}" if lat is not None else ""
    lng_part = f"{float(lng):.3f}" if lng is not None else ""
    city_part = (city or "").strip().lower()
    raw = f"{title_fp}|{time_part}|{lat_part}|{lng_part}|{city_part}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def compute_dedupe_key_from_event(event: dict) -> str | None:
    starts_at = event.get("starts_at")
    if not starts_at or not event.get("title"):
        return None
    if isinstance(starts_at, str):
        try:
            starts_at = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        except ValueError:
            return None
    return compute_dedupe_key(
        event.get("title") or "",
        starts_at,
        event.get("lat"),
        event.get("lng"),
        event.get("city"),
    )


def find_duplicate_event_id(
    conn: Connection,
    *,
    dedupe_key: str,
    title: str,
    starts_at: datetime,
    lat: float | None,
    lng: float | None,
    city: str | None,
    exclude_source: str | None = None,
    exclude_external_id: str | None = None,
) -> int | None:
    """Return existing event id if this post looks like the same event."""
    row = conn.execute(
        text(
            """
            SELECT id
            FROM events
            WHERE dedupe_key = :dedupe_key
              AND status NOT IN ('closed', 'canceled')
              AND NOT (source = :exclude_source AND external_id = :exclude_external_id)
            ORDER BY
              (referral_code IS NOT NULL AND btrim(referral_code) <> '') DESC,
              id ASC
            LIMIT 1
            """
        ),
        {
            "dedupe_key": dedupe_key,
            "exclude_source": exclude_source or "",
            "exclude_external_id": exclude_external_id or "",
        },
    ).fetchone()
    if row:
        return int(row[0])

    title_fp = _title_fingerprint(title)
    if not title_fp or starts_at is None:
        return None

    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)
    window_start = starts_at - timedelta(hours=1)
    window_end = starts_at + timedelta(hours=1)

    params = {
        "window_start": window_start,
        "window_end": window_end,
        "city": city,
        "exclude_source": exclude_source or "",
        "exclude_external_id": exclude_external_id or "",
    }
    fuzzy_sql = """
        SELECT id, title, lat, lng,
               (referral_code IS NOT NULL AND btrim(referral_code) <> '') AS has_referral
        FROM events
        WHERE status NOT IN ('closed', 'canceled')
          AND starts_at BETWEEN :window_start AND :window_end
          AND NOT (source = :exclude_source AND external_id = :exclude_external_id)
    """
    if city:
        fuzzy_sql += " AND city = :city"
    fuzzy_sql += " ORDER BY has_referral DESC, id ASC LIMIT 50"

    for candidate in conn.execute(text(fuzzy_sql), params):
        if not titles_likely_same(title, candidate.title or ""):
            continue
        if lat is not None and lng is not None and candidate.lat is not None and candidate.lng is not None:
            if _haversine_km(lat, lng, float(candidate.lat), float(candidate.lng)) > 2.0:
                continue
        return int(candidate.id)
    return None


def pick_preferred_event(events: list[dict]) -> dict:
    """Keep the best duplicate for display; partner/referral wins later too."""

    def _score(item: dict) -> tuple:
        referral = 1 if (item.get("referral_code") or "").strip() else 0
        source = item.get("source") or ""
        source_rank = 1 if source == "telegram" else 0
        return (referral, source_rank, -(item.get("id") or 0))

    return max(events, key=_score)


def dedupe_events_for_display(events: list[dict]) -> list[dict]:
    result: list[dict] = []
    for event in events:
        matched_idx = None
        for idx, kept in enumerate(result):
            same_key = (event.get("dedupe_key") and event.get("dedupe_key") == kept.get("dedupe_key")) or (
                compute_dedupe_key_from_event(event) == compute_dedupe_key_from_event(kept)
            )
            same_title_time = titles_likely_same(
                event.get("title") or "",
                kept.get("title") or "",
            ) and event.get("starts_at") == kept.get("starts_at")
            if same_key or same_title_time:
                matched_idx = idx
                break
        if matched_idx is None:
            result.append(event)
        else:
            result[matched_idx] = pick_preferred_event([result[matched_idx], event])
    return result


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * r * asin(sqrt(a))
