#!/usr/bin/env python3
"""
Скрипт для запуска BaliForum парсера
Запускается по расписанию для инжеста событий
"""

import os
import sys
from datetime import datetime

from dotenv import load_dotenv

# Добавляем текущую директорию в путь
sys.path.append(".")

from sqlalchemy import text

from database import get_engine, init_engine
from sources.baliforum import fetch
from utils.event_translation import translate_titles_batch
from utils.structured_logging import StructuredLogger
from utils.unified_events_service import UnifiedEventsService


def run_baliforum_ingest():
    """Запуск инжеста BaliForum событий"""
    start_time = datetime.now()

    print(f"🚀 Запуск BaliForum инжеста: {start_time}")

    # Инициализируем БД
    database_url = os.getenv("DATABASE_URL")
    init_engine(database_url)
    engine = get_engine()
    service = UnifiedEventsService(engine)

    try:
        # Получаем события
        print("📊 Получаем события от BaliForum...")
        events = fetch(limit=100)
        print(f"  Найдено событий: {len(events)}")

        if events:
            # 1. Подготавливаем события для сохранения
            prepared = []
            skipped_no_coords = 0
            for event in events:
                try:
                    # Проверяем координаты
                    if not event.lat or not event.lng:
                        skipped_no_coords += 1
                        continue

                    # Извлекаем venue и location_url из _raw_data если есть
                    venue = ""
                    location_url = ""
                    location_name = ""
                    place_name_from_maps = ""
                    if hasattr(event, "_raw_data") and event._raw_data:
                        venue = event._raw_data.get("venue", "") or ""
                        location_url = event._raw_data.get("location_url", "") or ""
                        place_name_from_maps = event._raw_data.get("place_name_from_maps", "") or ""
                        # ПРИОРИТЕТ: place_name_from_maps (из ссылки) > venue (из HTML)
                        location_name = place_name_from_maps or venue or ""

                    # Reverse geocoding ТОЛЬКО если:
                    # 1. НЕТ ссылки Google Maps (location_url пустая)
                    # 2. ИЛИ есть ссылка, но в ней НЕТ названия места (place_name_from_maps пустое)
                    # 3. И нет venue из HTML
                    # 4. И есть координаты
                    # НЕ используем reverse geocoding если есть ссылка с названием - чтобы не было путаницы!
                    generic_names = [
                        "",
                        "Место не указано",
                        "Локация",
                        "Место по ссылке",
                        "Место проведения",
                    ]
                    has_maps_link_with_name = (
                        location_url and place_name_from_maps and place_name_from_maps not in generic_names
                    )
                    needs_reverse_geocode = (
                        not has_maps_link_with_name  # Нет ссылки с названием
                        and (not location_name or location_name in generic_names)  # И нет другого названия
                        and event.lat
                        and event.lng
                    )

                    if needs_reverse_geocode:
                        try:
                            import asyncio

                            from utils.geo_utils import reverse_geocode

                            # Выполняем reverse geocoding синхронно
                            try:
                                asyncio.get_running_loop()
                                # Если loop уже запущен, используем ThreadPoolExecutor
                                import concurrent.futures

                                with concurrent.futures.ThreadPoolExecutor() as executor:
                                    future = executor.submit(asyncio.run, reverse_geocode(event.lat, event.lng))
                                    reverse_name = future.result(timeout=5)
                            except RuntimeError:
                                # Нет запущенного loop, используем asyncio.run
                                reverse_name = asyncio.run(reverse_geocode(event.lat, event.lng))

                            if reverse_name:
                                location_name = reverse_name
                                print(
                                    f"✅ Получено название места через reverse geocoding: "
                                    f"{location_name} для '{event.title[:50]}'"
                                )
                        except Exception as e:
                            print(f"⚠️ Ошибка при reverse geocoding для '{event.title[:50]}': {e}")

                    ext_id = event.external_id or event.url.split("/")[-1]
                    prepared.append(
                        {
                            "source": "baliforum",
                            "external_id": ext_id,
                            "title": event.title,
                            "description": event.description,
                            "starts_at_utc": event.starts_at,
                            "city": "bali",
                            "lat": event.lat,
                            "lng": event.lng,
                            "location_name": location_name,
                            "location_url": location_url,
                            "url": event.url,
                        }
                    )

                except Exception as e:
                    print(f"    ⚠️ Ошибка подготовки события: {e}")

            # 2. Пакетный перевод (ТЗ): один вызов API на все заголовки, которым нужен перевод
            title_en_map = {}
            if prepared:
                ext_ids = list({p["external_id"] for p in prepared})
                with engine.connect() as conn:
                    rows = conn.execute(
                        text("""
                            SELECT external_id, title_en
                            FROM events
                            WHERE source = 'baliforum' AND external_id = ANY(:ids)
                        """),
                        {"ids": ext_ids},
                    ).fetchall()
                has_title_en = {r[0] for r in rows if r[1] and str(r[1]).strip()}

                to_translate = [
                    (p["source"], p["external_id"], (p["title"] or "").strip())
                    for p in prepared
                    if p["external_id"] not in has_title_en and (p["title"] or "").strip()
                ]

                if to_translate:
                    titles = [t for _, _, t in to_translate]
                    results = translate_titles_batch(titles)
                    for (src, ext_id, _), title_en in zip(to_translate, results):
                        if title_en:
                            title_en_map[(src, ext_id)] = title_en
                    print(f"  📝 Пакетный перевод: {sum(1 for r in results if r)}/{len(to_translate)} заголовков")

            # 3. Сохраняем события (с предзаполненным title_en из batch)
            saved_count = 0
            errors = 0
            for p in prepared:
                try:
                    title_en = title_en_map.get((p["source"], p["external_id"]))
                    event_id = service.save_parser_event(
                        source=p["source"],
                        external_id=p["external_id"],
                        title=p["title"],
                        description=p["description"],
                        starts_at_utc=p["starts_at_utc"],
                        city=p["city"],
                        lat=p["lat"],
                        lng=p["lng"],
                        location_name=p["location_name"],
                        location_url=p["location_url"],
                        url=p["url"],
                        title_en=title_en,
                    )
                    if event_id:
                        saved_count += 1
                except Exception as e:
                    print(f"    ❌ Ошибка сохранения события: {e}")
                    errors += 1

            print(f"  Сохранено событий: {saved_count}")
            print(f"  Пропущено без координат: {skipped_no_coords}")
            print(f"  Ошибок: {errors}")

            # Логируем результат
            duration_ms = (datetime.now() - start_time).total_seconds() * 1000
            StructuredLogger.log_ingest(
                source="baliforum",
                region="bali",
                parsed=len(events),
                skipped_no_time=0,  # BaliForum парсер уже фильтрует
                skipped_no_coords=skipped_no_coords,
                upserted=saved_count,
                updated=0,
                duration_ms=duration_ms,
                errors=errors,
            )

        else:
            print("  ❌ Нет событий для сохранения")

    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
        import traceback

        traceback.print_exc()

        # Логируем ошибку
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        StructuredLogger.log_ingest(
            source="baliforum",
            region="bali",
            parsed=0,
            skipped_no_time=0,
            skipped_no_coords=0,
            upserted=0,
            updated=0,
            duration_ms=duration_ms,
            errors=1,
        )


if __name__ == "__main__":
    load_dotenv("app.local.env")
    run_baliforum_ingest()
