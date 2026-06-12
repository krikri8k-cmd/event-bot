"""Гео-резолв для Telegram ingest: task_places → Google Geocoding → opt-in default coords."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine

from utils.geo_utils import geocode_address
from utils.telegram_sources_service import TelegramSource

logger = logging.getLogger(__name__)


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


def _normalize_place_name(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"^@\s*", "", s)
    s = re.sub(r"\s+", " ", s)
    return s


def _geocode_queries(location_name: str, region: str) -> list[str]:
    """Несколько вариантов запроса — «Savaya Bali, bali» часто не находится в Google."""
    region_label = "Bali, Indonesia" if region == "bali" else region
    return list(
        dict.fromkeys(
            [
                f"{location_name}, {region_label}",
                f"{location_name}, Indonesia",
                location_name,
            ]
        )
    )


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


async def resolve_telegram_location(
    engine: Engine,
    source: TelegramSource,
    location_name: str | None,
) -> GeoResolveResult:
    name = _normalize_place_name(location_name or "")
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
) -> GeoResolveResult:
    """Sync wrapper for worker threads."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(resolve_telegram_location(engine, source, location_name))
    else:
        return loop.run_until_complete(resolve_telegram_location(engine, source, location_name))
