#!/usr/bin/env python3
"""
Тестирование парсера KudaGo с фильтром по датам
"""

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import load_settings
from database import get_engine, init_engine
from sources.kudago_source import KudaGoSource

# Включаем логирование
logging.basicConfig(level=logging.INFO)


async def test_kudago_date_filter():
    """Тестируем парсер KudaGo с фильтром по датам"""
    settings = load_settings()
    init_engine(settings.database_url)
    get_engine()

    print("🔍 ТЕСТИРОВАНИЕ KUDAGO С ФИЛЬТРОМ ПО ДАТАМ")
    print("=" * 50)

    # Проверяем настройки
    print(f"KUDAGO_ENABLED: {settings.kudago_enabled}")
    print(f"KUDAGO_DRY_RUN: {settings.kudago_dry_run}")

    if not settings.kudago_enabled:
        print("❌ KudaGo отключен!")
        return

    if settings.kudago_dry_run:
        print("⚠️ KudaGo в тестовом режиме (DRY_RUN)")
    else:
        print("✅ KudaGo в рабочем режиме")

    print()

    # Показываем временное окно
    moscow_tz = ZoneInfo("Europe/Moscow")
    utc_tz = ZoneInfo("UTC")
    now_moscow = datetime.now(moscow_tz)

    today_start = now_moscow.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_end = today_start + timedelta(days=1)

    today_start_utc = today_start.astimezone(utc_tz)
    tomorrow_end_utc = tomorrow_end.astimezone(utc_tz)

    print("📅 ВРЕМЕННОЕ ОКНО:")
    print(f"   Начало: {today_start_utc} (UTC)")
    print(f"   Конец: {tomorrow_end_utc} (UTC)")
    print(f"   Начало: {today_start} (Москва)")
    print(f"   Конец: {tomorrow_end} (Москва)")
    print()

    # Создаем источник
    source = KudaGoSource()

    # Координаты центра Москвы
    moscow_lat = 55.7558
    moscow_lng = 37.6173

    print(f"📍 Ищем события для координат: {moscow_lat}, {moscow_lng}")
    print()

    try:
        # Запускаем парсер
        events = await source.fetch_events(moscow_lat, moscow_lng, 15.0)

        print("✅ Парсер завершен!")
        print(f"📊 Получено событий: {len(events)}")

        if events:
            print()
            print("📝 Найденные события:")

            # Показываем события с актуальными датами
            today_events = []
            future_events = []

            for event in events:
                starts_at = event.get("starts_at_utc")
                if starts_at:
                    starts_at_moscow = starts_at.astimezone(moscow_tz)

                    if starts_at_moscow.date() == now_moscow.date():
                        today_events.append((event, starts_at_moscow))
                    elif starts_at_moscow > now_moscow:
                        future_events.append((event, starts_at_moscow))

            print(f"📅 Событий на СЕГОДНЯ ({now_moscow.date()}): {len(today_events)}")
            for event, time in today_events[:5]:  # Показываем первые 5
                title = event.get("title", "Без названия")
                location = event.get("location_name", "Место не указано")
                print(f"   - {title} в {time.strftime('%H:%M')} ({location})")

            print()
            print(f"📅 Событий на БУДУЩЕЕ: {len(future_events)}")
            for event, time in future_events[:5]:  # Показываем первые 5
                title = event.get("title", "Без названия")
                location = event.get("location_name", "Место не указано")
                print(f"   - {title} {time.strftime('%d.%m %H:%M')} ({location})")

        else:
            print("❌ События не найдены")
            print()
            print("💡 Возможные причины:")
            print("   - На сегодня нет событий в KudaGo")
            print("   - Фильтр по датам слишком строгий")
            print("   - Проблемы с API KudaGo")

    except Exception as e:
        print(f"❌ Ошибка парсера: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_kudago_date_filter())
