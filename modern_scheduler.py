#!/usr/bin/env python3
"""
Современный планировщик для автоматического пополнения событий
Использует новую архитектуру с UnifiedEventsService
"""

import logging
import time

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text

from config import load_settings
from database import get_engine, init_engine
from sources.baliforum import fetch as fetch_baliforum
from utils.event_translation import translate_titles_batch
from utils.unified_events_service import UnifiedEventsService

logger = logging.getLogger(__name__)


class ModernEventScheduler:
    """Современный планировщик событий"""

    def __init__(self):
        self.settings = load_settings()
        init_engine(self.settings.database_url)
        self.engine = get_engine()
        self.service = UnifiedEventsService(self.engine)
        self.scheduler = None

    def ingest_baliforum(self):
        """Парсинг событий с BaliForum через правильную архитектуру"""
        if not self.settings.enable_baliforum:
            logger.info("🌴 BaliForum отключен в настройках")
            return

        try:
            logger.info("🌴 Запуск парсинга BaliForum...")
            start_time = time.time()

            # Получаем события на сегодня и завтра
            # ВАЖНО: НЕ фильтруем по радиусу - парсим ВСЕ события со всего Бали
            # Сначала парсим главную страницу (события на сегодня)
            # Увеличиваем limit до 200 для парсинга большего количества событий
            raw_events = fetch_baliforum(limit=200)

            # Затем парсим страницу с фильтром по завтрашней дате
            from datetime import datetime, timedelta
            from zoneinfo import ZoneInfo

            tz_bali = ZoneInfo("Asia/Makassar")
            tomorrow_bali = (datetime.now(tz_bali) + timedelta(days=1)).date()
            tomorrow_str = tomorrow_bali.strftime("%Y-%m-%d")

            logger.info(f"🌴 Парсим события на завтра ({tomorrow_str})...")
            from sources.baliforum import fetch_baliforum_events

            # Увеличиваем limit до 200 для парсинга большего количества событий
            tomorrow_events = fetch_baliforum_events(limit=200, date_filter=tomorrow_str)
            # Конвертируем в RawEvent формат
            from event_apis import RawEvent

            for event in tomorrow_events:
                external_id = event.get("external_id", event["url"].rstrip("/").split("/")[-1])
                raw_event = RawEvent(
                    title=event["title"],
                    lat=event.get("lat") or 0.0,
                    lng=event.get("lng") or 0.0,
                    starts_at=event.get("start_time"),
                    source="baliforum",
                    external_id=external_id,
                    url=event["url"],
                    description=event.get("description"),
                )
                raw_events.append(raw_event)

            logger.info(f"🌴 Всего найдено событий: {len(raw_events)} (сегодня + завтра)")

            prepared = []
            skipped_no_coords = 0
            skipped_no_time = 0

            for event in raw_events:
                try:
                    # Проверяем время начала
                    if not event.starts_at:
                        skipped_no_time += 1
                        logger.debug(f"⏭️ Пропущено событие '{event.title}' - нет времени начала")
                        continue

                    # Проверяем координаты (как в оригинальном парсере)
                    if not event.lat or not event.lng:
                        skipped_no_coords += 1
                        logger.debug(
                            f"⏭️ Пропущено событие '{event.title}' - нет координат "
                            f"(lat={event.lat}, lng={event.lng})"
                        )
                        continue

                    # Логируем дату события для отладки
                    if event.starts_at:
                        from datetime import datetime, timedelta
                        from zoneinfo import ZoneInfo

                        now_bali = datetime.now(ZoneInfo("Asia/Makassar"))
                        event_date_bali = event.starts_at.astimezone(ZoneInfo("Asia/Makassar")).date()
                        today_bali = now_bali.date()
                        tomorrow_bali = today_bali + timedelta(days=1)

                        date_label = (
                            "сегодня"
                            if event_date_bali == today_bali
                            else "завтра"
                            if event_date_bali == tomorrow_bali
                            else f"{event_date_bali}"
                        )
                        logger.info(f"   📅 BaliForum событие: '{event.title}' - {date_label} ({event.starts_at})")

                    # Извлекаем venue и location_url из _raw_data если есть
                    venue = ""
                    location_url = ""
                    location_name = ""
                    place_name_from_maps = ""
                    place_id_from_maps = None
                    if hasattr(event, "_raw_data") and event._raw_data:
                        venue = event._raw_data.get("venue", "") or ""
                        location_url = event._raw_data.get("location_url", "") or ""
                        place_name_from_maps = event._raw_data.get("place_name_from_maps", "") or ""
                        place_id_from_maps = event._raw_data.get("place_id")
                        # ПРИОРИТЕТ: place_name_from_maps (из ссылки) > venue (из HTML)
                        location_name = place_name_from_maps or venue or ""

                    # Используем PlaceResolver для получения названия места:
                    # 1. Если есть place_id, но нет названия или название generic → используем get_place_details
                    # 2. Если нет place_id, но есть координаты и нет названия → используем nearby_search
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

                    # Если есть place_id, но нет названия или название generic → используем get_place_details
                    needs_place_resolver_by_place_id = place_id_from_maps and (
                        not location_name or location_name in generic_names
                    )

                    # Если нет place_id, но есть координаты и нет названия → используем nearby_search
                    needs_place_resolver_by_coords = (
                        not place_id_from_maps
                        and not has_maps_link_with_name
                        and (not location_name or location_name in generic_names)
                        and event.lat
                        and event.lng
                    )

                    needs_place_resolver = needs_place_resolver_by_place_id or needs_place_resolver_by_coords

                    if needs_place_resolver:
                        try:
                            import asyncio

                            from database import get_engine
                            from utils.place_resolver import PlaceResolver

                            engine = get_engine()
                            resolver = PlaceResolver(engine=engine)

                            # Выполняем PlaceResolver синхронно
                            try:
                                # Пробуем получить текущий loop
                                asyncio.get_running_loop()
                                # Если loop уже запущен, используем ThreadPoolExecutor
                                import concurrent.futures

                                def run_place_resolver():
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    try:
                                        # Если есть place_id, используем get_place_details напрямую
                                        if place_id_from_maps:
                                            return loop.run_until_complete(
                                                resolver.get_place_details(place_id_from_maps)
                                            )
                                        # Иначе используем resolve (nearby_search)
                                        return loop.run_until_complete(
                                            resolver.resolve(
                                                place_id=None,
                                                lat=event.lat,
                                                lng=event.lng,
                                            )
                                        )
                                    finally:
                                        loop.close()

                                with concurrent.futures.ThreadPoolExecutor() as executor:
                                    future = executor.submit(run_place_resolver)
                                    place_data = future.result(timeout=15)
                            except RuntimeError:
                                # Нет запущенного loop, используем asyncio.run
                                if place_id_from_maps:
                                    place_data = asyncio.run(resolver.get_place_details(place_id_from_maps))
                                else:
                                    place_data = asyncio.run(
                                        resolver.resolve(place_id=None, lat=event.lat, lng=event.lng)
                                    )

                            if place_data and place_data.get("name") and place_data["name"] not in generic_names:
                                location_name = place_data["name"]
                                # Обновляем place_id если его не было или если получили новый
                                if place_data.get("place_id"):
                                    place_id_from_maps = place_data["place_id"]
                                method = "get_place_details" if place_id_from_maps else "nearby_search"
                                logger.info(
                                    f"✅ Получено название места через PlaceResolver.{method}: "
                                    f"{location_name} (place_id: {place_id_from_maps}) для '{event.title[:50]}'"
                                )
                            elif place_data:
                                logger.debug(
                                    f"⚠️ PlaceResolver вернул generic название '{place_data.get('name')}', "
                                    f"пропускаем для '{event.title[:50]}'"
                                )
                        except Exception as e:
                            logger.warning(f"⚠️ Ошибка при PlaceResolver для '{event.title[:50]}': {e}")

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
                            "place_id": place_id_from_maps,
                        }
                    )

                except Exception as e:
                    logger.error(f"   ❌ Ошибка подготовки события '{event.title}': {e}")

            # Пакетный перевод (ТЗ): один вызов API на все заголовки
            title_en_map = {}
            if prepared:
                ext_ids = list({p["external_id"] for p in prepared})
                with self.engine.connect() as conn:
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
                    n_ok = sum(1 for r in results if r)
                    logger.info(f"   📝 Пакетный перевод: {n_ok}/{len(to_translate)} заголовков")

            # Сохраняем события
            saved_count = 0
            error_count = 0
            for p in prepared:
                try:
                    title_en = title_en_map.get((p["source"], p["external_id"]))
                    event_id = self.service.save_parser_event(
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
                        place_id=p.get("place_id"),
                        title_en=title_en,
                    )
                    if event_id:
                        saved_count += 1
                except Exception as e:
                    error_count += 1
                    logger.error(f"   ❌ Ошибка сохранения события '{p.get('title', '')}': {e}")

            duration = (time.time() - start_time) * 1000
            logger.info(
                f"   ✅ BaliForum: сохранено={saved_count}, "
                f"пропущено без времени={skipped_no_time}, "
                f"пропущено без координат={skipped_no_coords}, "
                f"ошибок={error_count}, время={duration:.0f}мс"
            )
            if skipped_no_time > 0 or skipped_no_coords > 0:
                logger.warning(
                    f"   ⚠️ BaliForum: пропущено {skipped_no_time + skipped_no_coords} событий "
                    f"из {len(raw_events)} найденных "
                    f"({skipped_no_time} без времени, {skipped_no_coords} без координат)"
                )

        except Exception as e:
            logger.error(f"   ❌ Ошибка парсинга BaliForum: {e}")

    async def ingest_kudago(self):
        """Парсинг событий с KudaGo через правильную архитектуру"""
        try:
            from config import load_settings

            settings = load_settings()

            if not settings.kudago_enabled:
                logger.info("🎭 KudaGo отключен в настройках")
                return

            logger.info("🎭 Запуск парсинга KudaGo...")
            start_time = time.time()

            # Координаты центров городов для парсинга
            cities_coords = [
                (55.7558, 37.6173, "moscow"),  # Москва
                (59.9343, 30.3351, "spb"),  # СПб
            ]

            total_saved = 0
            total_errors = 0

            from sources.kudago_source import KudaGoSource

            kudago_source = KudaGoSource()

            for lat, lng, city in cities_coords:
                try:
                    logger.info(f"   🌍 Парсим {city}...")

                    # Получаем события через KudaGo источник
                    # Увеличиваем радиус до 100км для парсинга большего количества событий в большом городе
                    events = await kudago_source.fetch_events(lat, lng, 100)  # 100км радиус для города

                    saved_count = 0
                    error_count = 0

                    for event in events:
                        try:
                            # Логируем дату события для отладки
                            if event.get("starts_at"):
                                from datetime import datetime, timedelta
                                from zoneinfo import ZoneInfo

                                now_msk = datetime.now(ZoneInfo("Europe/Moscow"))
                                event_date_msk = event.get("starts_at").astimezone(ZoneInfo("Europe/Moscow")).date()
                                today_msk = now_msk.date()
                                tomorrow_msk = today_msk + timedelta(days=1)

                                date_label = (
                                    "сегодня"
                                    if event_date_msk == today_msk
                                    else "завтра"
                                    if event_date_msk == tomorrow_msk
                                    else f"{event_date_msk}"
                                )
                                logger.info(
                                    f"   📅 KudaGo событие: '{event.get('title', '')}' - {date_label} "
                                    f"({event.get('starts_at')})"
                                )

                            # ПРАВИЛЬНАЯ АРХИТЕКТУРА: Сохраняем через UnifiedEventsService
                            event_id = self.service.save_parser_event(
                                source="kudago",
                                external_id=str(event.get("source_id", event.get("title", ""))),
                                title=event["title"],
                                description=event.get("description", ""),
                                starts_at_utc=event["starts_at"],
                                city=event["city"],
                                lat=event.get("lat", 0.0),
                                lng=event.get("lon", 0.0),
                                location_name=event.get("venue_name", ""),
                                location_url=event.get("address", ""),
                                url=event.get("source_url", ""),
                            )

                            if event_id:
                                saved_count += 1

                        except Exception as e:
                            error_count += 1
                            logger.error(
                                f"   ❌ Ошибка сохранения KudaGo события '{event.get('title', 'Unknown')}': {e}"
                            )

                    total_saved += saved_count
                    total_errors += error_count

                    logger.info(f"   ✅ {city}: сохранено={saved_count}, ошибок={error_count}")

                except Exception as e:
                    total_errors += 1
                    logger.error(f"   ❌ Ошибка парсинга {city}: {e}")

            duration = (time.time() - start_time) * 1000
            logger.info(
                f"   ✅ KudaGo: всего сохранено={total_saved}, " f"ошибок={total_errors}, время={duration:.0f}мс"
            )

        except Exception as e:
            logger.error(f"   ❌ Ошибка парсинга KudaGo: {e}")

    async def ingest_ai_events(self):
        """Генерация AI событий через правильную архитектуру"""
        if not self.settings.ai_parse_enable:
            logger.info("🤖 AI парсинг отключен в настройках")
            return

        try:
            logger.info("🤖 Запуск AI генерации событий...")
            start_time = time.time()

            # Координаты центра Бали
            bali_coords = [
                (-8.6705, 115.2126),  # Denpasar
                (-8.5069, 115.2625),  # Ubud
                (-8.6482, 115.1342),  # Canggu
                (-8.7089, 115.1681),  # Seminyak
            ]

            import hashlib
            from datetime import datetime

            from ai_utils import fetch_ai_events_nearby

            total_ai_events = 0
            error_count = 0

            for lat, lng in bali_coords:
                try:
                    ai_events = await fetch_ai_events_nearby(lat, lng)

                    for event in ai_events:
                        try:
                            # Парсим время
                            starts_at = datetime.strptime(event["time_local"], "%Y-%m-%d %H:%M")

                            # Создаем стабильный external_id
                            raw_id = f"ai_{event['title']}_{event['time_local']}_{lat}_{lng}"
                            external_id = hashlib.sha1(raw_id.encode()).hexdigest()[:16]

                            # ПРАВИЛЬНАЯ АРХИТЕКТУРА: Сохраняем через UnifiedEventsService
                            event_id = self.service.save_parser_event(
                                source="ai",
                                external_id=external_id,
                                title=event["title"],
                                description=event.get("description", ""),
                                starts_at_utc=starts_at,
                                city="bali",
                                lat=event["lat"],
                                lng=event["lng"],
                                location_name=event.get("location_name", ""),
                                location_url=event.get("location_url", ""),
                                url=event.get("community_link", ""),
                            )

                            if event_id:
                                total_ai_events += 1

                        except Exception as e:
                            error_count += 1
                            logger.error(f"   ❌ Ошибка сохранения AI события '{event.get('title', 'Unknown')}': {e}")

                except Exception as e:
                    error_count += 1
                    logger.error(f"   ❌ Ошибка AI парсинга для ({lat}, {lng}): {e}")

            duration = (time.time() - start_time) * 1000
            logger.info(f"   ✅ AI: создано={total_ai_events}, ошибок={error_count}, время={duration:.0f}мс")

        except Exception as e:
            logger.error(f"   ❌ Ошибка AI парсинга: {e}")

    def cleanup_old_events(self):
        """Очистка старых событий"""
        try:
            logger.info("🧹 Очистка старых событий...")

            cities = ["bali", "moscow", "spb"]
            total_deleted = 0

            for city in cities:
                deleted = self.service.cleanup_old_events(city)
                total_deleted += deleted

            logger.info(f"   ✅ Очищено {total_deleted} старых событий")

        except Exception as e:
            logger.error(f"   ❌ Ошибка очистки: {e}")

    def run_full_ingest(self):
        """Полный цикл обновления событий"""
        logger.info("🚀 === НАЧАЛО ЦИКЛА ОБНОВЛЕНИЯ СОБЫТИЙ ===")
        start_time = time.time()

        # 1. Парсим BaliForum (для Бали)
        if self.settings.enable_baliforum:
            self.ingest_baliforum()
        else:
            logger.info("🌴 BaliForum пропущен (отключен в настройках)")

        # KudaGo теперь запускается отдельно по своему расписанию (см. start())

        # 3. Генерируем AI события (если включено)
        if self.settings.ai_generate_synthetic:
            import asyncio

            # Используем новый event loop с явным закрытием для освобождения ресурсов
            # ВАЖНО: loop.run_until_complete() уже дожидается завершения всех задач,
            # поэтому мы просто закрываем loop после завершения
            loop = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                # run_until_complete дожидается полного завершения функции и всех её задач
                loop.run_until_complete(self.ingest_ai_events())
            except Exception as e:
                logger.error(f"❌ Ошибка в ingest_ai_events: {e}")
            finally:
                # Закрываем loop только после полного завершения всех операций
                if loop and not loop.is_closed():
                    try:
                        # Даем время на завершение всех pending операций (если есть)
                        # Но не отменяем их - они должны завершиться естественным образом
                        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                        if pending:
                            # Ждем завершения pending задач (но не отменяем их!)
                            # Это безопасно, т.к. run_until_complete уже завершился
                            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    except Exception:
                        pass
                    finally:
                        loop.close()
        else:
            logger.info("🤖 AI генерация пропущена (отключена в настройках)")

        # 4. Очищаем старые события
        self.cleanup_old_events()

        duration = time.time() - start_time
        logger.info(f"✅ === ЦИКЛ ЗАВЕРШЕН ЗА {duration:.1f}с ===")

    def run_kudago_ingest(self):
        """Отдельный цикл парсинга KudaGo для Москвы и СПб"""
        logger.info("🎭 === НАЧАЛО ЦИКЛА ПАРСИНГА KUDAGO (МОСКВА, СПБ) ===")
        start_time = time.time()

        if self.settings.kudago_enabled:
            import asyncio

            # Используем новый event loop с явным закрытием для освобождения ресурсов
            # ВАЖНО: loop.run_until_complete() уже дожидается завершения всех задач,
            # поэтому мы просто закрываем loop после завершения
            loop = None
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                # run_until_complete дожидается полного завершения функции и всех её задач
                loop.run_until_complete(self.ingest_kudago())
            except Exception as e:
                logger.error(f"❌ Ошибка в ingest_kudago: {e}")
            finally:
                # Закрываем loop только после полного завершения всех операций
                if loop and not loop.is_closed():
                    try:
                        # Даем время на завершение всех pending операций (если есть)
                        # Но не отменяем их - они должны завершиться естественным образом
                        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                        if pending:
                            # Ждем завершения pending задач (но не отменяем их!)
                            # Это безопасно, т.к. run_until_complete уже завершился
                            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    except Exception:
                        pass
                    finally:
                        loop.close()
        else:
            logger.info("🎭 KudaGo пропущен (отключен в настройках)")

        duration = time.time() - start_time
        logger.info(f"✅ === ЦИКЛ KUDAGO ЗАВЕРШЕН ЗА {duration:.1f}с ===")

    def cleanup_expired_tasks(self):
        """Очистка просроченных заданий"""
        try:
            from tasks_service import mark_tasks_as_expired

            logger.info("🧹 Запуск очистки просроченных заданий...")
            expired_count = mark_tasks_as_expired()

            if expired_count > 0:
                logger.info(f"✅ Помечено как истекшие: {expired_count} заданий")
            else:
                logger.info("ℹ️ Просроченных заданий не найдено")

        except Exception as e:
            logger.error(f"❌ Ошибка очистки просроченных заданий: {e}")

    def cleanup_expired_community_events(self):
        """Очистка старых событий сообществ (перенос в архив)"""
        try:
            from utils.community_events_service import CommunityEventsService

            logger.info("🧹 Очистка старых событий сообществ...")
            community_service = CommunityEventsService()
            # Очищаем события старше 1 дня (они переносятся в архив)
            deleted_count = community_service.cleanup_expired_events(days_old=1)

            if deleted_count > 0:
                logger.info(f"   ✅ Архивировано и удалено {deleted_count} старых событий сообществ")
            else:
                logger.info("   ℹ️ Старых событий сообществ не найдено")

        except Exception as e:
            logger.error(f"❌ Ошибка очистки событий сообществ: {e}")

    def check_removed_chats(self):
        """Проверка чатов, из которых бот мог быть удален"""
        try:
            from datetime import datetime

            from aiogram import Bot
            from sqlalchemy import select

            from config import load_settings
            from database import ChatSettings

            logger.info("🔍 Проверка чатов на удаление бота...")

            settings = load_settings()
            if not settings.telegram_token:
                logger.warning("⚠️ TELEGRAM_TOKEN не настроен, пропускаем проверку")
                return

            # Создаем async бота для проверки
            bot = Bot(token=settings.telegram_token)

            # Получаем engine и создаем session
            from database import async_engine, async_session_maker

            if not async_engine or not async_session_maker:
                logger.warning("⚠️ Async engine не инициализирован, пропускаем проверку")
                return

            async def check_chats_async():
                checked_count = 0
                removed_count = 0
                updated_admins_count = 0

                async with async_session_maker() as session:
                    # Получаем все активные чаты
                    result = await session.execute(select(ChatSettings).where(ChatSettings.bot_status == "active"))
                    chats = result.scalars().all()

                    logger.info(f"   Найдено {len(chats)} активных чатов для проверки")

                    for chat in chats:
                        checked_count += 1
                        try:
                            # Пробуем получить информацию о чате
                            # Если бот удален, это вызовет ошибку
                            await bot.get_chat(chat.chat_id)

                            # Обновляем админов
                            try:
                                import json

                                from utils.community_events_service import CommunityEventsService

                                community_service = CommunityEventsService()
                                admin_ids = await community_service.get_cached_admin_ids(bot, chat.chat_id)
                                admin_count = len(admin_ids)

                                # Обновляем только если изменилось
                                current_admin_ids = json.loads(chat.admin_ids) if chat.admin_ids else []
                                if set(admin_ids) != set(current_admin_ids):
                                    chat.admin_ids = json.dumps(admin_ids) if admin_ids else None
                                    chat.admin_count = admin_count
                                    updated_admins_count += 1
                                    logger.info(f"   📝 Обновлены админы для чата {chat.chat_id}: count={admin_count}")

                            except Exception as admin_error:
                                logger.warning(
                                    f"   ⚠️ Не удалось обновить админов для чата {chat.chat_id}: {admin_error}"
                                )

                        except Exception as e:
                            error_msg = str(e).lower()
                            # Проверяем, не был ли бот удален
                            if (
                                "bot was kicked" in error_msg
                                or "bot was removed" in error_msg
                                or "chat not found" in error_msg
                                or "forbidden" in error_msg
                            ):
                                logger.warning(f"   🚫 Бот удален из чата {chat.chat_id}")
                                chat.bot_status = "removed"
                                chat.bot_removed_at = datetime.utcnow()
                                removed_count += 1

                    await session.commit()
                    logger.info(
                        f"   ✅ Проверено {checked_count} чатов, удаленных найдено: {removed_count}, "
                        f"админов обновлено: {updated_admins_count}"
                    )

                await bot.session.close()

            # Запускаем async функцию
            import asyncio

            asyncio.run(check_chats_async())

        except Exception as e:
            logger.error(f"❌ Ошибка проверки удаленных чатов: {e}")

    def send_community_reminders(self):
        """Отправка напоминаний о Community событиях за 24 часа"""
        try:
            import asyncio

            from utils.community_reminders import send_24h_reminders_sync

            bot_token = self.settings.telegram_token
            if not bot_token:
                logger.error("❌ TELEGRAM_TOKEN не установлен, пропускаем напоминания")
                return

            logger.info("🔔 Запуск проверки напоминаний о Community событиях...")

            # Запускаем async функцию в синхронном контексте
            # Проверяем, есть ли уже запущенный event loop
            try:
                asyncio.get_running_loop()
                # Если loop уже запущен, используем ThreadPoolExecutor
                import concurrent.futures

                def run_reminders():
                    # Создаем новый event loop в отдельном потоке
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(send_24h_reminders_sync(bot_token))
                    finally:
                        loop.close()

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_reminders)
                    future.result(timeout=300)  # 5 минут таймаут
            except RuntimeError:
                # Нет запущенного loop, используем asyncio.run
                asyncio.run(send_24h_reminders_sync(bot_token))
        except Exception as e:
            logger.error(f"❌ Ошибка отправки напоминаний: {e}")
            import traceback

            logger.error(traceback.format_exc())

    def send_event_start_notifications(self):
        """Отправка уведомлений о начале Community событий"""
        try:
            import asyncio

            from utils.community_reminders import send_event_start_notifications_sync

            bot_token = self.settings.telegram_token
            if not bot_token:
                logger.error("❌ TELEGRAM_TOKEN не установлен, пропускаем уведомления о начале")
                return

            logger.info("🔔 Запуск проверки уведомлений о начале Community событий...")

            # Запускаем async функцию в синхронном контексте
            try:
                asyncio.get_running_loop()
                import concurrent.futures

                def run_notifications():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        return loop.run_until_complete(send_event_start_notifications_sync(bot_token))
                    finally:
                        loop.close()

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_notifications)
                    future.result(timeout=300)
            except RuntimeError:
                asyncio.run(send_event_start_notifications_sync(bot_token))
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомлений о начале: {e}")
            import traceback

            logger.error(traceback.format_exc())

    def start(self):
        """Запуск планировщика"""
        if self.scheduler and self.scheduler.running:
            logger.warning("⚠️ Планировщик уже запущен, пропускаем повторный запуск")
            # Проверяем, что все задачи зарегистрированы
            jobs = self.scheduler.get_jobs()
            job_ids = [job.id for job in jobs]
            logger.info(f"📋 Зарегистрированные задачи: {job_ids}")
            if "event-start-notifications" not in job_ids:
                logger.warning("⚠️ Задача 'event-start-notifications' не найдена! Добавляем...")
                self.scheduler.add_job(
                    self.send_event_start_notifications,
                    "interval",
                    minutes=5,
                    id="event-start-notifications",
                    max_instances=1,
                    coalesce=True,
                )
                logger.info("✅ Задача 'event-start-notifications' добавлена")

            # Запускаем проверку напоминаний и уведомлений сразу для тестирования
            logger.info("🔔 Запускаем проверку напоминаний и уведомлений сразу после старта...")
            try:
                self.send_community_reminders()
                self.send_event_start_notifications()
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при запуске проверки сразу после старта: {e}")
                import traceback

                logger.error(traceback.format_exc())
            return

        self.scheduler = BackgroundScheduler(timezone="UTC")

        # Основной цикл парсинга событий BaliForum (2 раза в день по времени Бали)
        # Утренний запуск: 18:02 UTC = 00:02 Бали (начало нового дня по Бали)
        self.scheduler.add_job(
            self.run_full_ingest,
            "cron",
            hour=18,
            minute=2,
            id="modern-ingest-morning",
            max_instances=1,
            coalesce=True,
        )
        # Вечерний запуск: 04:02 UTC = 12:02 Бали (середина дня по Бали)
        self.scheduler.add_job(
            self.run_full_ingest,
            "cron",
            hour=4,
            minute=2,
            id="modern-ingest-evening",
            max_instances=1,
            coalesce=True,
        )

        # Парсинг KudaGo (Москва и СПб) - отдельное расписание по времени МСК
        # Утренний запуск: 21:02 UTC = 00:02 МСК (начало нового дня по МСК)
        self.scheduler.add_job(
            self.run_kudago_ingest,
            "cron",
            hour=21,
            minute=2,
            id="kudago-ingest-morning",
            max_instances=1,
            coalesce=True,
        )
        # Вечерний запуск: 09:02 UTC = 12:02 МСК (середина дня по МСК)
        self.scheduler.add_job(
            self.run_kudago_ingest,
            "cron",
            hour=9,
            minute=2,
            id="kudago-ingest-evening",
            max_instances=1,
            coalesce=True,
        )

        # Очистка старых событий каждые 6 часов
        self.scheduler.add_job(
            self.cleanup_old_events, "interval", hours=6, id="cleanup-cycle", max_instances=1, coalesce=True
        )

        # Очистка просроченных заданий каждые 2 часа
        self.scheduler.add_job(
            self.cleanup_expired_tasks, "interval", hours=2, id="tasks-cleanup", max_instances=1, coalesce=True
        )

        # Очистка старых событий сообществ (архивация) каждые 6 часов
        # Открытые события: архивируются по дате начала (starts_at < NOW() - 1 day)
        # Закрытые события: архивируются по времени закрытия (updated_at < NOW() - 24 hours)
        self.scheduler.add_job(
            self.cleanup_expired_community_events,
            "interval",
            hours=6,
            id="community-events-cleanup",
            max_instances=1,
            coalesce=True,
        )

        # Проверка удаленных чатов каждые 24 часа
        self.scheduler.add_job(
            self.check_removed_chats, "interval", hours=24, id="chat-status-check", max_instances=1, coalesce=True
        )

        # Напоминания о Community событиях за 24 часа - проверяем каждые 30 минут
        # Окно времени 30 минут гарантирует, что события не будут пропущены
        # и снижает нагрузку на систему по сравнению с проверкой каждые 15 минут
        self.scheduler.add_job(
            self.send_community_reminders,
            "interval",
            minutes=30,
            id="community-reminders",
            max_instances=1,
            coalesce=True,
        )

        # Уведомления о начале события - проверяем каждые 5 минут
        self.scheduler.add_job(
            self.send_event_start_notifications,
            "interval",
            minutes=5,
            id="event-start-notifications",
            max_instances=1,
            coalesce=True,
        )
        logger.info("   ✅ Зарегистрирована задача: уведомления о начале событий (каждые 5 минут)")

        self.scheduler.start()
        logger.info("🚀 Современный планировщик запущен!")
        logger.info("   📅 Полный цикл: каждые 12 часов (2 раза в день)")
        logger.info("   🌴 BaliForum (Бали) + 🎭 KudaGo (Москва, СПб)")
        logger.info("   🧹 Очистка событий: каждые 6 часов")
        logger.info("   ⏰ Очистка заданий: каждые 2 часа")
        logger.info("   🏘️ Архивация событий сообществ: каждые 6 часов")
        logger.info("   🔍 Проверка удаленных чатов: каждые 24 часа")
        logger.info("   🔔 Напоминания о событиях: каждые 30 минут")
        logger.info("   🎉 Уведомления о начале событий: каждые 5 минут")

        # Показываем следующее время выполнения задач
        jobs = self.scheduler.get_jobs()
        for job in jobs:
            if job.id in ["community-reminders", "event-start-notifications"]:
                next_run = job.next_run_time
                if next_run:
                    from datetime import UTC, datetime

                    now = datetime.now(UTC)
                    time_until = (next_run - now).total_seconds() / 60
                    logger.info(f"   ⏰ Следующий запуск '{job.id}': {next_run} " f"(через {time_until:.1f} минут)")
                else:
                    logger.warning(f"   ⚠️ Задача '{job.id}' не имеет следующего времени запуска")

        # Запускаем первый цикл сразу
        self.run_full_ingest()

        # Запускаем проверку напоминаний и уведомлений сразу для тестирования
        logger.info("🔔 Запускаем проверку напоминаний и уведомлений сразу после старта...")
        try:
            self.send_community_reminders()
            self.send_event_start_notifications()
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при запуске проверки сразу после старта: {e}")

    def stop(self):
        """Остановка планировщика"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("🛑 Планировщик остановлен")


# Глобальный экземпляр
_modern_scheduler = None


def get_modern_scheduler() -> ModernEventScheduler:
    """Получить экземпляр современного планировщика"""
    global _modern_scheduler
    if _modern_scheduler is None:
        _modern_scheduler = ModernEventScheduler()
    return _modern_scheduler


def start_modern_scheduler():
    """Запустить современный планировщик"""
    scheduler = get_modern_scheduler()
    scheduler.start()


if __name__ == "__main__":
    # Ручной запуск для тестирования
    logging.basicConfig(level=logging.INFO)
    scheduler = ModernEventScheduler()
    scheduler.run_full_ingest()
