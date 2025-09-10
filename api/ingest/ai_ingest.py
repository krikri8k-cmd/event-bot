#!/usr/bin/env python3
"""
AI-пайплайн для парсинга событий и загрузки в БД
"""

import argparse
import hashlib
import json
import os
from typing import Any

from sqlalchemy import create_engine, text

from api.ai_extractor import call_openai_for_events, extract_main_text, fetch_html
from api.normalize import geocode_one, to_utc_iso
from config import load_settings

settings = load_settings()
MAX_URLS = int(os.getenv("AI_INGEST_MAX_URLS", "20"))
MAX_EVENTS_PER_URL = int(os.getenv("AI_INGEST_MAX_EVENTS_PER_URL", "20"))
SOURCE_TAG = os.getenv("AI_INGEST_SOURCE_TAG", "ai")

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)


def canonical_key(e: dict[str, Any]) -> str:
    """Создает канонический ключ для дедупликации."""
    title = (e.get("title") or "").strip().lower()
    start = (e.get("start") or "").strip()
    venue = (e.get("venue_name") or "").strip().lower()
    base = f"{title}|{start}|{venue}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def upsert_event(conn, e: dict[str, Any], url: str):
    """Upsert события в БД."""
    start_utc = to_utc_iso(e.get("start"))
    to_utc_iso(e.get("end"))

    # геокодинг при необходимости
    lat = e.get("lat")
    lon = e.get("lon")
    if not lat or not lon:
        q = " ".join(filter(None, [e.get("venue_name"), e.get("address"), e.get("city"), e.get("country")]))
        lat, lon = geocode_one(q)

    conn.execute(
        text("""
    INSERT INTO events
      (title, description, starts_at, time_utc, location_name, lat, lng, source, url, city, country)
    VALUES
      (:title, :description, :starts_at, :time_utc, :location_name, :lat, :lng, :source, :url, :city, :country)
    ON CONFLICT (title, starts_at, location_name) DO UPDATE SET
      description = EXCLUDED.description,
      time_utc = EXCLUDED.time_utc,
      lat = COALESCE(EXCLUDED.lat, events.lat),
      lng = COALESCE(EXCLUDED.lng, events.lng),
      url = EXCLUDED.url,
      city = EXCLUDED.city,
      country = EXCLUDED.country
    """),
        dict(
            title=e.get("title"),
            description=e.get("description"),
            starts_at=start_utc,
            time_utc=start_utc,
            location_name=e.get("venue_name"),
            lat=lat,
            lon=lon,
            source=SOURCE_TAG,
            url=url,
            city=e.get("city"),
            country=e.get("country", "Indonesia"),
        ),
    )


def process_url(conn, url: str, city_hint: str | None):
    """Обрабатывает один URL."""
    html = fetch_html(url)
    text = extract_main_text(html)
    events = call_openai_for_events(text, url, city_hint, MAX_EVENTS_PER_URL)

    seen = set()
    inserted = 0

    for e in events:
        if not e.get("title") or not e.get("start"):
            continue
        key = canonical_key(e)
        if key in seen:
            continue
        seen.add(key)
        upsert_event(conn, e, url)
        inserted += 1
    return inserted


def run_from_seed(seed_path="seeds/ai_sources.json", limit=None, dry_run=False):
    """Запускает пайплайн из файла источников."""
    with open(seed_path, encoding="utf-8") as f:
        sources = json.load(f)

    # Ограничиваем количество URL если указан limit
    if limit:
        sources = sources[:limit]
        print(f"[INFO] Ограничение: обрабатываем только {limit} URL")

    if dry_run:
        print("[DRY-RUN] Режим тестирования - записи в БД не производится")

    total = 0

    if dry_run:
        # В dry-run режиме не используем соединение с БД
        for i, src in enumerate(sources):
            url = src["url"]
            city = src.get("city")
            try:
                print(f"[DRY-RUN] Обрабатываем: {url}")
                # Здесь можно добавить логику для тестирования без записи
                total += 1  # Просто считаем обработанные URL
            except Exception as e:
                print(f"[ERR] {url}: {e}")
    else:
        # Обычный режим с записью в БД
        with engine.begin() as conn:
            for i, src in enumerate(sources):
                url = src["url"]
                city = src.get("city")
                try:
                    n = process_url(conn, url, city)
                    print(f"[OK] {url} -> {n} events")
                    total += n
                except Exception as e:
                    print(f"[ERR] {url}: {e}")

    print(f"TOTAL INSERTED: {total}")
    return total


def main():
    parser = argparse.ArgumentParser(description="AI-пайплайн для парсинга событий")
    parser.add_argument("--limit", type=int, help="Ограничить количество обрабатываемых URL")
    parser.add_argument("--dry-run", action="store_true", help="Тестовый режим без записи в БД")
    parser.add_argument("--seed", default="seeds/ai_sources.json", help="Путь к файлу источников")

    args = parser.parse_args()

    run_from_seed(args.seed, args.limit, args.dry_run)


if __name__ == "__main__":
    main()
