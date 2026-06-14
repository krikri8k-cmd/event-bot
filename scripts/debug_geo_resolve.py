#!/usr/bin/env python3
"""
Отладка гео-резолва для Telegram ingest: ссылки, task_places, геокодинг по названию.

Примеры:
    python scripts/debug_geo_resolve.py "IMAX в ICON"
    python scripts/debug_geo_resolve.py "IMAX в ICON" --ref-url https://maps.app.goo.gl/F65wLhwR5CTzKCvd6
    python scripts/debug_geo_resolve.py "Savaya Bali" --region bali
    python scripts/debug_geo_resolve.py "IMAX в ICON" --entity "Кино здесь|https://maps.app.goo.gl/Cinema" --entity "здесь|https://maps.app.goo.gl/Dinner"
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import create_engine, text  # noqa: E402

from config import load_settings  # noqa: E402
from utils.geo_utils import geocode_address, haversine_km, parse_google_maps_link  # noqa: E402
from utils.telegram_geo_resolver import (  # noqa: E402
    _geocode_queries,
    collect_maps_url_candidates,
    pick_best_maps_url,
    resolve_telegram_location,
)
from utils.telegram_sources_service import TelegramSource  # noqa: E402

DEFAULT_RAW = (
    "Балийцы - го в кино!\n"
    "Иду сегодня на 21:15 в IMAX в ICON на Спилберга\n"
    "Кино здесь:\n\n"
    "Перед кино - ужин здесь:\n"
    "Пицца у них - шикарная"
)


def _parse_entity(value: str) -> tuple[str, str]:
    if "|" not in value:
        raise argparse.ArgumentTypeError("Формат --entity: 'якорь|https://maps...'")
    anchor, url = value.split("|", 1)
    anchor, url = anchor.strip(), url.strip()
    if not url.startswith("http"):
        raise argparse.ArgumentTypeError(f"URL в --entity должен начинаться с http: {url!r}")
    return url, anchor


def _dist_line(lat: float, lng: float, ref: tuple[float, float] | None) -> str:
    if not ref:
        return ""
    km = haversine_km(lat, lng, ref[0], ref[1])
    flag = "OK" if km <= 3 else "FAR" if km <= 15 else "WRONG"
    return f"  dist={km:.2f} km [{flag}]"


def _lookup_task_places(engine, name: str, region: str) -> None:
    print("\n=== task_places (БД) ===")
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, name, lat, lng, google_maps_url
                FROM task_places
                WHERE is_active = TRUE
                  AND region = :region
                  AND name ILIKE :pattern
                ORDER BY length(name) ASC
                LIMIT 8
            """),
            {"region": region, "pattern": f"%{name}%"},
        ).fetchall()
    if not rows:
        print("  (совпадений нет)")
        return
    for row in rows:
        print(f"  id={row.id} name={row.name!r}")
        print(f"    lat/lng=({row.lat}, {row.lng})")
        if row.google_maps_url:
            print(f"    url={row.google_maps_url[:90]}")


async def _run_geocode_queries(name: str, region: str, ref: tuple[float, float] | None) -> None:
    print("\n=== geocode по названию (_geocode_queries) ===")
    if not load_settings().google_maps_api_key:
        print("  [SKIP] GOOGLE_MAPS_API_KEY не задан")
        return

    any_ok = False
    for query in _geocode_queries(name, region):
        coords = await geocode_address(query, region_bias=region)
        if coords:
            any_ok = True
            print(f"  OK  {query!r}")
            print(f"      -> ({coords[0]:.6f}, {coords[1]:.6f}){_dist_line(coords[0], coords[1], ref)}")
        else:
            print(f"  MISS {query!r}")
    if not any_ok:
        print("  → ни один вариант запроса не вернул координаты")


async def _run_maps_candidates(
    name: str,
    raw_text: str,
    entity_links: list[tuple[str, str]],
    ref: tuple[float, float] | None,
) -> None:
    print("\n=== выбор Google Maps URL ===")
    candidates = collect_maps_url_candidates(
        location_name=name,
        raw_text=raw_text,
        entity_links=entity_links or None,
    )
    if not candidates:
        print("  (кандидатов нет — пойдём в geocode/task_places)")
        return

    for url, anchor, bonus in candidates:
        print(f"  candidate bonus={bonus}: anchor={anchor!r}")
        print(f"    {url[:100]}")

    best = pick_best_maps_url(candidates, raw_text=raw_text)
    print(f"  → pick_best_maps_url: {best}")

    if best:
        parsed = await parse_google_maps_link(best)
        if parsed and parsed.get("lat") is not None:
            lat, lng = float(parsed["lat"]), float(parsed["lng"])
            print(f"  → parsed: ({lat:.6f}, {lng:.6f}) name={parsed.get('name')!r}{_dist_line(lat, lng, ref)}")
        else:
            print("  → parse_google_maps_link: не удалось")


async def _run_full_resolve(
    engine,
    name: str,
    region: str,
    raw_text: str,
    entity_links: list[tuple[str, str]],
    ref: tuple[float, float] | None,
) -> None:
    print("\n=== resolve_telegram_location (как в ingest) ===")
    source = TelegramSource(
        id=1,
        chat_id=-5179811176,
        username=None,
        title="debug",
        is_active=True,
        trust_level="moderated",
        default_city=region,
        default_country="ID",
        timezone="Asia/Makassar",
        allow_default_coords=False,
        default_lat=None,
        default_lng=None,
        default_contact=None,
        default_categories=[],
        partner_id=None,
        last_processed_message_id=None,
    )
    result = await resolve_telegram_location(
        engine,
        source,
        name,
        raw_text=raw_text,
        entity_links=entity_links or None,
    )
    if not result.ok:
        print(f"  REJECT reason={result.reject_reason}")
        return
    print(f"  method={result.method}")
    print(f"  name={result.resolved_name!r}")
    print(f"  coords=({result.lat:.6f}, {result.lng:.6f}){_dist_line(result.lat, result.lng, ref)}")
    if result.location_url:
        print(f"  url={result.location_url[:100]}")


def _has_real_database() -> bool:
    url = (os.getenv("DATABASE_URL") or "").strip()
    return bool(url) and "127.0.0.1:5432/debug" not in url and "localhost:5432/debug" not in url


async def main_async(args: argparse.Namespace) -> int:
    # load_settings() требует DATABASE_URL; dotenv мог оставить пустую строку
    if not (os.getenv("DATABASE_URL") or "").strip():
        os.environ["DATABASE_URL"] = "postgresql://debug:debug@127.0.0.1:5432/debug"

    settings = load_settings()
    ref: tuple[float, float] | None = None

    print("=== debug_geo_resolve ===")
    print(f"  name={args.name!r} region={args.region}")

    if not settings.google_maps_api_key:
        print("\n[WARN] GOOGLE_MAPS_API_KEY не задан — геокодинг по названию не сработает")

    if args.ref_url:
        print("\n=== эталон (--ref-url) ===")
        parsed = await parse_google_maps_link(args.ref_url.strip())
        if not parsed or parsed.get("lat") is None:
            print(f"  [ERROR] не удалось распарсить: {args.ref_url}")
            return 1
        ref = (float(parsed["lat"]), float(parsed["lng"]))
        print(f"  name={parsed.get('name')!r}")
        print(f"  coords=({ref[0]:.6f}, {ref[1]:.6f})")

    entity_links = list(args.entity or [])
    raw_text = args.raw_text if args.raw_text is not None else DEFAULT_RAW

    await _run_maps_candidates(args.name, raw_text, entity_links, ref)
    await _run_geocode_queries(args.name, args.region, ref)

    if _has_real_database():
        try:
            engine = create_engine(settings.database_url)
            _lookup_task_places(engine, args.name, args.region)
            await _run_full_resolve(engine, args.name, args.region, raw_text, entity_links, ref)
        except Exception as e:
            print(f"\n[WARN] БД недоступна ({e}) — task_places и full resolve пропущены")
    else:
        print("\n[SKIP] DATABASE_URL не задан — task_places и resolve_telegram_location пропущены")
        print("       (геокодинг и parse_google_maps_link всё равно отработали выше)")

    if ref:
        print("\n=== подсказка ===")
        print("  dist <= 3 km  — координаты совпадают с эталоном")
        print("  dist <= 15 km — близко, но может не попасть в радиус 5 km")
        print("  dist > 15 km  — скорее всего не то место (как было с IMAX)")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Отладка гео-резолва Telegram ingest")
    parser.add_argument("name", help="Название места из поста / LLM (например «IMAX в ICON»)")
    parser.add_argument("--region", default="bali", help="Регион источника (default: bali)")
    parser.add_argument(
        "--ref-url",
        help="Эталонная Google Maps ссылка для сравнения расстояния",
    )
    parser.add_argument(
        "--entity",
        action="append",
        type=_parse_entity,
        metavar="ANCHOR|URL",
        help="Вшитая ссылка из Telegram entity, можно несколько раз",
    )
    parser.add_argument(
        "--raw-text",
        default=None,
        help="Текст поста (по умолчанию — пример с кино и ужином)",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
