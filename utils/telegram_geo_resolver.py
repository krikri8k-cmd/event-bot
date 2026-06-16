"""Гео-резолв для Telegram ingest: task_places → Google Geocoding → opt-in default coords."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from utils.geo_utils import geocode_address, normalize_maps_link, parse_google_maps_link
from utils.telegram_sources_service import TelegramSource

logger = logging.getLogger(__name__)

_MAPS_URL_RE = re.compile(
    r"https?://(?:maps\.app\.goo\.gl|goo\.gl/maps|www\.google\.com/maps|maps\.google\.com)[^\s\)>\"']+"
)

_VENUE_KEYWORDS = (
    "кино",
    "cinema",
    "imax",
    "xxi",
    "icon",
    "театр",
    "кинотеатр",
    "локаци",
    "location",
    "место",
    "venue",
    "карта",
    "maps",
    "address",
    "адрес",
    "здесь",
    "here",
)
_FOOD_KEYWORDS = (
    "ужин",
    "dinner",
    "обед",
    "lunch",
    "пицц",
    "pizza",
    "ресторан",
    "restaurant",
    "бар",
    "bar",
    "кафе",
    "cafe",
    "еда",
    "food",
    "kitchen",
    "кухн",
)
_CINEMA_NAME_MARKERS = ("imax", "xxi", "icon", "cinema", "кино", "кинотеатр")


@dataclass
class GeoResolveResult:
    ok: bool
    lat: float | None = None
    lng: float | None = None
    location_url: str | None = None
    place_id: str | None = None
    resolved_name: str | None = None
    method: str | None = None
    reject_reason: str | None = None


def _find_maps_url(*texts: str | None) -> str | None:
    for chunk in texts:
        if not chunk:
            continue
        match = _MAPS_URL_RE.search(chunk)
        if match:
            return match.group(0).rstrip(".,;)")
    return None


def _context_around_anchor(raw_text: str, anchor: str, window: int = 48) -> str:
    if not raw_text or not anchor:
        return raw_text or ""
    idx = raw_text.lower().find(anchor.lower())
    if idx < 0:
        return raw_text
    start = max(0, idx - window)
    end = min(len(raw_text), idx + len(anchor) + window)
    return raw_text[start:end]


def _score_maps_candidate(url: str, anchor: str, raw_text: str, *, source_bonus: int = 0) -> int:
    if not _is_maps_url(url):
        return -10_000
    score = source_bonus
    anchor_low = (anchor or "").lower()
    ctx = f"{anchor_low} {_context_around_anchor(raw_text, anchor)}".lower()
    for kw in _VENUE_KEYWORDS:
        if kw in anchor_low:
            score += 30
        elif kw in ctx:
            score += 8
    for kw in _FOOD_KEYWORDS:
        if kw in anchor_low:
            score -= 40
        elif kw in ctx:
            score -= 12
    return score


def collect_maps_url_candidates(
    *,
    location_name: str | None,
    raw_text: str | None,
    entity_links: list[tuple[str, str]] | None = None,
) -> list[tuple[str, str, int]]:
    """(url, anchor, source_bonus) — порядок в сообщении сохраняется."""
    out: list[tuple[str, str, int]] = []
    seen: set[str] = set()

    def add(url: str, anchor: str, bonus: int) -> None:
        cleaned = normalize_maps_link(url.rstrip(".,;)"))
        if not cleaned or cleaned in seen:
            return
        seen.add(cleaned)
        out.append((cleaned, anchor or cleaned, bonus))

    if location_name and _is_maps_url(location_name):
        add(location_name.strip(), location_name.strip(), 120)

    for url, anchor in entity_links or []:
        add(url, anchor, 80)

    if raw_text:
        for match in _MAPS_URL_RE.finditer(raw_text):
            add(match.group(0), match.group(0), 20)

    return out


def pick_best_maps_url(
    candidates: list[tuple[str, str, int]],
    *,
    raw_text: str = "",
) -> str | None:
    maps = [(u, a, b) for u, a, b in candidates if _is_maps_url(u)]
    if not maps:
        return None
    if len(maps) == 1:
        return maps[0][0]

    scored: list[tuple[int, int, str]] = []
    for idx, (url, anchor, bonus) in enumerate(maps):
        scored.append((_score_maps_candidate(url, anchor, raw_text, source_bonus=bonus), idx, url))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][2]


def _is_maps_url(value: str) -> bool:
    low = (value or "").lower()
    return "goo.gl" in low or "google.com/maps" in low or "maps.google.com" in low


def _normalize_place_name(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"^@\s*", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _geocode_queries(location_name: str, region: str) -> list[str]:
    """Несколько вариантов запроса — «Savaya Bali, bali» часто не находится в Google."""
    region_label = "Bali, Indonesia" if region == "bali" else region
    norm = _normalize_place_name(location_name)
    queries = [
        f"{norm}, {region_label}",
        f"{norm}, Indonesia",
        norm,
    ]
    low = norm.lower()
    if any(marker in low for marker in _CINEMA_NAME_MARKERS):
        compact = re.sub(r"\s+в\s+", " ", norm, flags=re.IGNORECASE)
        queries = list(
            dict.fromkeys(
                [
                    f"{norm} cinema, {region_label}",
                    f"{compact} cinema, {region_label}",
                    f"Cinema {compact}, {region_label}",
                    f"{compact}, Denpasar, Bali, Indonesia",
                    *queries,
                ]
            )
        )
    return queries


def _lookup_task_place(engine: Engine, location_name: str, region: str) -> GeoResolveResult | None:
    norm = _normalize_place_name(location_name)
    if len(norm) < 2:
        return None

    with engine.connect() as conn:
        exact = conn.execute(
            text("""
                SELECT id, name, lat, lng, google_maps_url
                FROM task_places
                WHERE is_active = TRUE
                  AND region = :region
                  AND lower(name) = lower(:name)
                LIMIT 1
            """),
            {"region": region, "name": norm},
        ).fetchone()
        if exact:
            return GeoResolveResult(
                ok=True,
                lat=float(exact.lat),
                lng=float(exact.lng),
                location_url=exact.google_maps_url,
                place_id=str(exact.id),
                resolved_name=exact.name,
                method="task_places_exact",
            )

        patterns = [f"%{norm}%"]
        first_word = norm.split()[0] if norm.split() else ""
        if len(first_word) >= 4 and first_word.lower() != norm.lower():
            patterns.append(f"%{first_word}%")

        candidates = []
        for pattern in patterns:
            rows = conn.execute(
                text("""
                    SELECT id, name, lat, lng, google_maps_url
                    FROM task_places
                    WHERE is_active = TRUE
                      AND region = :region
                      AND name ILIKE :pattern
                    ORDER BY length(name) ASC
                    LIMIT 5
                """),
                {"region": region, "pattern": pattern},
            ).fetchall()
            candidates.extend(rows)
            if candidates:
                break

    if len(candidates) == 1:
        row = candidates[0]
        return GeoResolveResult(
            ok=True,
            lat=float(row.lat),
            lng=float(row.lng),
            location_url=row.google_maps_url,
            place_id=str(row.id),
            resolved_name=row.name,
            method="task_places_ilike",
        )

    if len(candidates) > 1:
        for row in candidates:
            if row.name.lower() == norm.lower():
                return GeoResolveResult(
                    ok=True,
                    lat=float(row.lat),
                    lng=float(row.lng),
                    location_url=row.google_maps_url,
                    place_id=str(row.id),
                    resolved_name=row.name,
                    method="task_places_ilike_best",
                )
    return None


async def _geocode_location(location_name: str, region: str) -> tuple[float, float] | None:
    for query in _geocode_queries(location_name, region):
        coords = await geocode_address(query, region_bias=region)
        if coords:
            logger.info("Geocoded %r via query %r", location_name, query)
            return coords
    logger.warning("Geocode failed for %r (region=%s)", location_name, region)
    return None


async def _resolve_maps_url(url: str) -> GeoResolveResult | None:
    parsed = await parse_google_maps_link(url)
    if not parsed:
        return None
    lat, lng = parsed.get("lat"), parsed.get("lng")
    if lat is None or lng is None:
        return None
    return GeoResolveResult(
        ok=True,
        lat=float(lat),
        lng=float(lng),
        location_url=url,
        resolved_name=(parsed.get("name") or "Место на карте"),
        method="google_maps_link",
    )


async def resolve_telegram_location(
    engine: Engine,
    source: TelegramSource,
    location_name: str | None,
    raw_text: str | None = None,
    entity_links: list[tuple[str, str]] | None = None,
) -> GeoResolveResult:
    candidates = collect_maps_url_candidates(
        location_name=location_name,
        raw_text=raw_text,
        entity_links=entity_links,
    )
    maps_url = pick_best_maps_url(candidates, raw_text=raw_text or "")
    if not maps_url:
        maps_url = _find_maps_url(location_name, raw_text)

    if maps_url:
        from_maps = await _resolve_maps_url(maps_url)
        if from_maps and from_maps.ok:
            from_maps.method = "google_maps_link"
            if entity_links and any(maps_url == u for u, _ in entity_links):
                from_maps.method = "google_maps_entity_link"
            logger.info(
                "Resolved maps URL %r -> (%s, %s) method=%s",
                maps_url[:80],
                from_maps.lat,
                from_maps.lng,
                from_maps.method,
            )
            return from_maps

    name = _normalize_place_name(location_name or "")
    if _is_maps_url(name):
        name = ""
    if not name:
        if source.allow_default_coords and source.default_lat is not None and source.default_lng is not None:
            return GeoResolveResult(
                ok=True,
                lat=float(source.default_lat),
                lng=float(source.default_lng),
                resolved_name=source.title,
                method="default_coords",
            )
        return GeoResolveResult(ok=False, reject_reason="no_location_name")

    region = source.default_city or "bali"
    from_db = _lookup_task_place(engine, name, region)
    if from_db and from_db.ok:
        return from_db

    coords = await _geocode_location(name, region)
    if coords:
        lat, lng = coords
        return GeoResolveResult(
            ok=True,
            lat=lat,
            lng=lng,
            resolved_name=name,
            method="google_geocode",
        )

    if source.allow_default_coords and source.default_lat is not None and source.default_lng is not None:
        return GeoResolveResult(
            ok=True,
            lat=float(source.default_lat),
            lng=float(source.default_lng),
            resolved_name=name,
            method="default_coords_fallback",
        )

    return GeoResolveResult(ok=False, reject_reason="no_coordinates")


def resolve_telegram_location_sync(
    engine: Engine,
    source: TelegramSource,
    location_name: str | None,
    *,
    raw_text: str | None = None,
    entity_links: list[tuple[str, str]] | None = None,
) -> GeoResolveResult:
    """Sync wrapper for worker threads."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            resolve_telegram_location(
                engine,
                source,
                location_name,
                raw_text=raw_text,
                entity_links=entity_links,
            )
        )
    else:
        return loop.run_until_complete(
            resolve_telegram_location(
                engine,
                source,
                location_name,
                raw_text=raw_text,
                entity_links=entity_links,
            )
        )
