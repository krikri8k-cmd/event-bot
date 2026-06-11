"""
УНИФИЦИРОВАННЫЙ сервис для работы с событиями через единую таблицу events
"""

import logging
import threading
import time
from datetime import datetime

from sqlalchemy import text

from utils.event_translation import (
    detect_event_language,
    translate_event_to_english,
    translate_event_to_russian,
)
from utils.simple_timezone import get_today_start_utc, get_tomorrow_start_utc
from utils.structured_logging import StructuredLogger

logger = logging.getLogger(__name__)


class UnifiedEventsService:
    """Унифицированный сервис для работы с единой таблицей events"""

    def __init__(self, engine):
        self.engine = engine

    def search_events_today(
        self,
        city: str,
        user_lat: float | None = None,
        user_lng: float | None = None,
        radius_km: float = 15,
        date_offset: int = 0,
        message_id: str | None = None,
    ) -> list[dict]:
        """
        Поиск событий из единой таблицы events

        Args:
            city: Название города
            user_lat: Широта пользователя
            user_lng: Долгота пользователя
            radius_km: Радиус поиска в километрах
            date_offset: Смещение даты (0 = сегодня, 1 = завтра, по умолчанию 0)
            message_id: ID сообщения для логирования
        """
        from datetime import timedelta

        start_time = time.time()

        # Получаем временные границы для города с учетом смещения даты
        if date_offset == 0:
            # Сегодня
            start_utc = get_today_start_utc(city)
            end_utc = get_tomorrow_start_utc(city)
        elif date_offset == 1:
            # Завтра
            start_utc = get_tomorrow_start_utc(city)
            # Конец завтрашнего дня = начало послезавтрашнего дня
            end_utc = get_tomorrow_start_utc(city) + timedelta(days=1)
        else:
            # Для других значений используем общую формулу
            base_start = get_today_start_utc(city)
            start_utc = base_start + timedelta(days=date_offset)
            end_utc = start_utc + timedelta(days=1)

        date_label = "сегодня" if date_offset == 0 else "завтра" if date_offset == 1 else f"+{date_offset} дней"
        logger.debug(
            "🔍 SEARCH: city=%s, user_lat=%s, user_lng=%s, radius_km=%s, date=%s",
            city,
            user_lat,
            user_lng,
            radius_km,
            date_label,
        )

        with self.engine.connect() as conn:
            # Важно: фильтруем события, которые начались не более 3 часов назад
            # (starts_at >= NOW() - INTERVAL '3 hours')
            # и события в пределах запрошенного дня (starts_at >= start_utc AND starts_at < end_utc)
            # Это позволяет видеть события в течение 3 часов после начала
            # (для долгих событий: вечеринки, выставки)
            if user_lat and user_lng:
                # Поиск с координатами и радиусом
                # Добавляем фильтр по city, если указан
                city_filter = ""
                params = {
                    "start_utc": start_utc,
                    "end_utc": end_utc,
                    "user_lat": user_lat,
                    "user_lng": user_lng,
                    "radius_km": radius_km,
                }
                if city:
                    city_filter = "AND city = :city"
                    params["city"] = city

                query = text(f"""
                    SELECT source, id, title, description, title_en, description_en, location_name_en,
                           starts_at, city, lat, lng, location_name,
                           location_url, url as event_url,
                           organizer_id, organizer_username, max_participants,
                           current_participants, status, created_at_utc,
                           community_name, chat_id, location_name as venue_name,
                           location_name as address, place_id,
                           '' as geo_hash, starts_at as starts_at_normalized
                    FROM events
                    WHERE starts_at >= :start_utc
                    AND starts_at < :end_utc
                    AND starts_at >= NOW() - INTERVAL '3 hours'
                    AND lat IS NOT NULL AND lng IS NOT NULL
                    AND status NOT IN ('closed', 'canceled', 'draft')
                    {city_filter}
                    AND 6371 * acos(
                        GREATEST(-1, LEAST(1,
                            cos(radians(:user_lat)) * cos(radians(lat)) *
                            cos(radians(lng) - radians(:user_lng)) +
                            sin(radians(:user_lat)) * sin(radians(lat))
                        ))
                    ) <= :radius_km
                    ORDER BY starts_at
                """)

                result = conn.execute(query, params)
            else:
                # Поиск без координат
                # Добавляем фильтр по city, если указан
                city_filter = ""
                params = {
                    "start_utc": start_utc,
                    "end_utc": end_utc,
                }
                if city:
                    city_filter = "AND city = :city"
                    params["city"] = city

                query = text(f"""
                    SELECT source, id, title, description, title_en, description_en, location_name_en,
                           starts_at, city, lat, lng, location_name,
                           location_url, url as event_url,
                           organizer_id, organizer_username, max_participants,
                           current_participants, status, created_at_utc,
                           community_name, chat_id, location_name as venue_name,
                           location_name as address, place_id,
                           '' as geo_hash, starts_at as starts_at_normalized
                    FROM events
                    WHERE starts_at >= :start_utc
                    AND starts_at < :end_utc
                    AND starts_at >= NOW() - INTERVAL '3 hours'
                    AND status NOT IN ('closed', 'canceled', 'draft')
                    {city_filter}
                    ORDER BY starts_at
                """)

                result = conn.execute(query, params)

            events = []
            found_user = 0
            found_parser = 0

            for row in result:
                # Определяем source_type для совместимости с существующим кодом
                source_type = "user" if row[0] == "user" else "parser"

                # Подсчитываем по источникам
                if row[0] == "user":
                    found_user += 1
                else:
                    found_parser += 1

                event_data = {
                    "source_type": source_type,
                    "source": row[0],
                    "id": row[1],
                    "title": row[2],
                    "description": row[3],
                    "title_en": row[4] if len(row) > 4 else None,
                    "description_en": row[5] if len(row) > 5 else None,
                    "location_name_en": row[6] if len(row) > 6 else None,
                    "starts_at": row[7],
                    "city": row[8],
                    "lat": row[9],
                    "lng": row[10],
                    "location_name": row[11],
                    "location_url": row[12],
                    "event_url": row[13],
                    "organizer_id": row[14],
                    "organizer_username": row[15],
                    "max_participants": row[16],
                    "current_participants": row[17],
                    "status": row[18],
                    "created_at_utc": row[19],
                    "community_name": row[20] if len(row) > 20 else None,
                    "chat_id": row[21] if len(row) > 21 else None,
                    "venue_name": row[22] if len(row) > 22 else None,
                    "address": row[23] if len(row) > 23 else None,
                    "place_id": row[24] if len(row) > 24 else None,
                }

                # Логируем пользовательские события
                if row[0] == "user":
                    logger.info(
                        f"🔍 DB EVENT: title='{row[2]}', source='{row[0]}', "
                        f"organizer_id={row[14]}, organizer_username='{row[15]}'"
                    )

                events.append(event_data)

            # Если не найдено событий с координатами, проверяем соответствие координат региону
            # и если координаты не соответствуют региону, пробуем поиск без радиуса
            if not events and user_lat and user_lng:
                from utils.simple_timezone import get_city_from_coordinates

                detected_city = get_city_from_coordinates(user_lat, user_lng)
                # Fallback поиск только если координаты определены и не соответствуют региону
                if detected_city is not None and detected_city != city:
                    logger.warning(
                        f"⚠️ Координаты пользователя ({user_lat}, {user_lng}) не соответствуют региону '{city}'. "
                        f"Определен регион: '{detected_city}'. Пробуем поиск без радиуса..."
                    )
                    # Fallback: поиск без радиуса по временным границам региона
                    fallback_query = text("""
                        SELECT source, id, title, description, title_en, description_en, location_name_en,
                               starts_at, city, lat, lng, location_name,
                               location_url, url as event_url,
                               organizer_id, organizer_username, max_participants,
                               current_participants, status, created_at_utc,
                               community_name, chat_id, location_name as venue_name,
                               location_name as address, place_id,
                               '' as geo_hash, starts_at as starts_at_normalized
                        FROM events
                        WHERE starts_at >= :start_utc
                        AND starts_at < :end_utc
                        AND starts_at >= NOW() - INTERVAL '3 hours'
                        AND status NOT IN ('closed', 'canceled', 'draft')
                        ORDER BY starts_at
                        LIMIT 50
                    """)
                    fallback_result = conn.execute(
                        fallback_query,
                        {
                            "start_utc": start_utc,
                            "end_utc": end_utc,
                        },
                    )
                    # Обрабатываем результаты fallback поиска
                    for row in fallback_result:
                        source_type = "user" if row[0] == "user" else "parser"
                        event_data = {
                            "source_type": source_type,
                            "source": row[0],
                            "id": row[1],
                            "title": row[2],
                            "description": row[3],
                            "title_en": row[4] if len(row) > 4 else None,
                            "description_en": row[5] if len(row) > 5 else None,
                            "location_name_en": row[6] if len(row) > 6 else None,
                            "starts_at": row[7],
                            "city": row[8],
                            "lat": row[9],
                            "lng": row[10],
                            "location_name": row[11],
                            "location_url": row[12],
                            "event_url": row[13],
                            "organizer_id": row[14],
                            "organizer_username": row[15],
                            "max_participants": row[16],
                            "current_participants": row[17],
                            "status": row[18],
                            "created_at_utc": row[19],
                            "community_name": row[20] if len(row) > 20 else None,
                            "chat_id": row[21] if len(row) > 21 else None,
                            "venue_name": row[22] if len(row) > 22 else None,
                            "address": row[23] if len(row) > 23 else None,
                            "place_id": row[24] if len(row) > 24 else None,
                        }
                        events.append(event_data)
                    if events:
                        logger.info(
                            f"✅ Fallback поиск нашел {len(events)} событий для региона '{city}' "
                            f"(координаты пользователя не соответствуют региону)"
                        )

            # Логируем результат поиска
            empty_reason = None
            if not events:
                if user_lat and user_lng:
                    empty_reason = "no_events_in_radius"
                else:
                    empty_reason = "no_events_today"

            # Логируем результаты поиска по городам
            cities_found = {}
            for event in events:
                event_city = event.get("city", "unknown")
                cities_found[event_city] = cities_found.get(event_city, 0) + 1

            logger.debug("🔍 SEARCH RESULT: city=%s, cities_found=%s", city, cities_found)

            StructuredLogger.log_search(
                region=city,
                radius_km=radius_km if user_lat and user_lng else 0,
                user_lat=user_lat or 0,
                user_lng=user_lng or 0,
                found_total=len(events),
                found_user=found_user,
                found_parser=found_parser,
                message_id=message_id,
                empty_reason=empty_reason,
                duration_ms=(time.time() - start_time) * 1000,
            )

            return events

    def get_events_stats(self, city: str) -> dict:
        """Статистика событий из единой таблицы"""
        start_utc = get_today_start_utc(city)
        end_utc = get_tomorrow_start_utc(city)

        with self.engine.connect() as conn:
            # Общая статистика
            total_result = conn.execute(
                text("""
                SELECT COUNT(*) FROM events
                WHERE city = :city
                AND starts_at >= :start_utc
                AND starts_at < :end_utc
            """),
                {"city": city, "start_utc": start_utc, "end_utc": end_utc},
            ).fetchone()

            # Статистика по источникам
            source_result = conn.execute(
                text("""
                SELECT source, COUNT(*) FROM events
                WHERE city = :city
                AND starts_at >= :start_utc
                AND starts_at < :end_utc
                GROUP BY source
            """),
                {"city": city, "start_utc": start_utc, "end_utc": end_utc},
            ).fetchall()

            # Подсчитываем пользовательские и парсерные события
            parser_events = 0
            user_events = 0

            for source, count in source_result:
                if source == "user":
                    user_events = count
                else:
                    parser_events += count

            return {
                "city": city,
                "parser_events": parser_events,
                "user_events": user_events,
                "total_events": total_result[0],
                "date_range": f"{start_utc.isoformat()} - {end_utc.isoformat()}",
            }

    def create_user_event(
        self,
        organizer_id: int,
        title: str,
        description: str,
        starts_at_utc: datetime,
        city: str,
        lat: float,
        lng: float,
        location_name: str,
        location_url: str = None,
        max_participants: int = None,
        chat_id: int = None,
        organizer_username: str = None,
        source: str = "user",
        external_id: str | None = None,
        community_name: str | None = None,
        title_en: str | None = None,
        description_en: str | None = None,
    ) -> int:
        """
        Создание пользовательского события в единую таблицу events.
        Если переданы title_en/description_en (например после перевода в боте), они сохраняются сразу;
        иначе запускается фоновый перевод RU→EN/EN→RU с последующим UPDATE.
        """
        with self.engine.begin() as conn:
            # Создаем событие напрямую в events (с EN-полями, если уже переведено)
            user_event_query = text("""
                INSERT INTO events (
                    source, external_id, event_source, title, title_en, description, description_en, starts_at, ends_at,
                    url, location_name, location_url, lat, lng, country, city,
                    organizer_id, organizer_username, max_participants, current_participants,
                    participants_ids, status, created_at_utc, updated_at_utc, is_generated_by_ai, chat_id,
                    community_name
                )
                VALUES (
                    :source, :external_id, 'user', :title, :title_en, :description, :description_en, :starts_at, NULL,
                    NULL, :location_name, :location_url, :lat, :lng, :country, :city,
                    :organizer_id, :organizer_username, :max_participants, 0,
                    NULL, 'open', NOW(), NOW(), false, :chat_id, :community_name
                )
                RETURNING id
            """)

            country = "ID" if city and city.lower() == "bali" else "RU"

            if external_id is None:
                # Генерируем уникальный external_id для пользовательского события
                import random
                import time

                # Используем микросекунды + случайное число для уникальности
                timestamp_ms = int(time.time() * 1000000)  # микросекунды
                random_suffix = random.randint(1000, 9999)  # случайное число
                external_id_value = f"user_{organizer_id}_{timestamp_ms}_{random_suffix}"
            else:
                external_id_value = external_id

            user_result = conn.execute(
                user_event_query,
                {
                    "source": source,
                    "external_id": external_id_value,
                    "organizer_id": organizer_id,
                    "organizer_username": organizer_username,
                    "title": title,
                    "title_en": title_en,
                    "description": description,
                    "description_en": description_en,
                    "starts_at": starts_at_utc,
                    "city": city,
                    "lat": lat,
                    "lng": lng,
                    "location_name": location_name,
                    "location_url": location_url,
                    "max_participants": max_participants,
                    "country": country,
                    "chat_id": chat_id,
                    "community_name": community_name,
                },
            )

            user_event_id = user_result.fetchone()[0]

            # Обновляем счетчик созданных событий (World версия)
            conn.execute(
                text("""
                UPDATE users
                SET events_created_world = events_created_world + 1,
                    updated_at_utc = NOW()
                WHERE id = :organizer_id
            """),
                {"organizer_id": organizer_id},
            )

            print(f"✅ Создано пользовательское событие ID {user_event_id}: '{title}'")

        # Автоперевод только если EN-поля не переданы (перевод уже сделан в боте до сохранения)
        en_provided = (title_en is not None and (title_en or "").strip()) or (
            description_en is not None and (description_en or "").strip()
        )
        if en_provided:
            logger.debug("create_user_event: EN-поля переданы, фоновый перевод не запускаем (id=%s)", user_event_id)
            return user_event_id

        # Автоперевод пользовательского события: RU→EN или EN→RU в фоне
        def _translate_and_update():
            try:
                lang = detect_event_language(title, description or "")
                if lang == "ru":
                    trans = translate_event_to_english(
                        title,
                        description=(description or "").strip() or None,
                        location_name=(location_name or "").strip() or None,
                    )
                    # Локация не переводится — в _en пишем оригинал
                    loc_en = (location_name or "").strip() or trans.get("location_name_en")
                    if trans.get("title_en") or trans.get("description_en") or loc_en:
                        with self.engine.begin() as conn:
                            conn.execute(
                                text("""
                                    UPDATE events
                                    SET title_en = COALESCE(:title_en, title_en),
                                        description_en = COALESCE(:description_en, description_en),
                                        location_name_en = COALESCE(:location_name_en, location_name_en)
                                    WHERE id = :event_id
                                """),
                                {
                                    "event_id": user_event_id,
                                    "title_en": trans.get("title_en"),
                                    "description_en": trans.get("description_en"),
                                    "location_name_en": loc_en,
                                },
                            )
                        logger.debug(
                            "Пользовательское событие переведено: [RU] -> [EN] (id=%s)",
                            user_event_id,
                        )
                        logger.info(
                            "create_user_event: обновлены EN-поля для события id=%s (title_en=%s)",
                            user_event_id,
                            bool(trans.get("title_en")),
                        )
                    else:
                        logger.debug(
                            "create_user_event: перевод для id=%s не получен (API недоступен или пустой ответ)",
                            user_event_id,
                        )
                else:
                    trans_ru = translate_event_to_russian(
                        title,
                        description=(description or "").strip() or None,
                        location_name=(location_name or "").strip() or None,
                    )
                    with self.engine.begin() as conn:
                        conn.execute(
                            text("""
                                UPDATE events
                                SET title = COALESCE(:title_ru, title),
                                    description = COALESCE(:description_ru, description),
                                    location_name = COALESCE(:location_name_ru, location_name),
                                    title_en = :title_en,
                                    description_en = :description_en,
                                    location_name_en = :location_name_en
                                WHERE id = :event_id
                            """),
                            {
                                "event_id": user_event_id,
                                "title_ru": trans_ru.get("title"),
                                "description_ru": trans_ru.get("description"),
                                "location_name_ru": trans_ru.get("location_name"),
                                "title_en": title,
                                "description_en": description or None,
                                "location_name_en": location_name or None,
                            },
                        )
                    logger.debug(
                        "Пользовательское событие переведено: [EN] -> [RU] (id=%s)",
                        user_event_id,
                    )
                    logger.info(
                        "create_user_event: обновлены поля (EN: оригинал в _en, RU: перевод в title/description) id=%s",
                        user_event_id,
                    )
            except Exception as e:
                logger.warning("create_user_event: фоновый перевод для id=%s не удался: %s", user_event_id, e)

        t = threading.Thread(target=_translate_and_update, daemon=True)
        t.start()

        return user_event_id

    def save_parser_event(
        self,
        source: str,
        external_id: str,
        title: str,
        description: str,
        starts_at_utc: datetime,
        city: str,
        lat: float,
        lng: float,
        location_name: str = None,
        location_url: str = None,
        url: str = None,
        place_id: str = None,
        title_en: str = None,
        description_en: str = None,
        location_name_en: str = None,
        ends_at_utc: datetime | None = None,
        status: str = "open",
        community_name: str | None = None,
        community_link: str | None = None,
        chat_id: int | None = None,
        organizer_username: str | None = None,
        referral_code: str | None = None,
    ) -> int:
        """
        Сохранение парсерного события в единую таблицу events.
        При создании или при изменении текста вызывается перевод RU→EN (title_en, description_en, location_name_en).
        При ошибке API перевода _en остаются NULL.
        """
        with self.engine.begin() as conn:
            existing_row = conn.execute(
                text("""
                SELECT id, title, description, title_en, description_en, location_name_en
                FROM events
                WHERE source = :source AND external_id = :external_id
            """),
                {"source": source, "external_id": external_id},
            ).fetchone()

            country = "ID" if city == "bali" else "RU"
            is_ai = source == "ai"

            # Ленивый перевод (ТЗ): переводим только один раз — когда title_en в базе ещё NULL.
            # Если title_en передан снаружи (например из batch), используем его и не вызываем API.
            passed_en = title_en is not None
            existing_title_en = existing_row[3] if existing_row and len(existing_row) > 3 else None
            existing_has_title_en = bool(existing_title_en and (existing_title_en or "").strip())
            need_translation = not passed_en and (not existing_row or not existing_has_title_en)

            if passed_en:
                # Передан title_en снаружи (batch) — description/location оставляем из БД при наличии
                if description_en is None and existing_row and len(existing_row) > 4:
                    description_en = existing_row[4]
                if location_name_en is None and existing_row and len(existing_row) > 5:
                    location_name_en = existing_row[5]
            elif existing_row and existing_has_title_en:
                # В базе уже есть перевод — никогда не вызываем OpenAI повторно
                logger.debug("[TRANSLATION-SKIP] Using existing EN for external_id=%s", external_id)
                title_en = existing_row[3]
            elif need_translation:
                # Новая запись или существующая с title_en NULL — вызываем перевод (догоняющий для старых)
                trans = translate_event_to_english(
                    title=title or "",
                    description=description,
                    location_name=location_name,
                )
                # Пустой ответ не пишем в БД — оставляем NULL для повтора
                title_en = (
                    trans.get("title_en") if trans.get("title_en") else (existing_row[3] if existing_row else None)
                )
                description_en = (
                    trans.get("description_en")
                    if trans.get("description_en")
                    else (existing_row[4] if existing_row and len(existing_row) > 4 else None)
                )
                # Локация не переводится — всегда оригинал (Google Maps style)
                location_name_en = location_name or (
                    existing_row[5] if existing_row and len(existing_row) > 5 else None
                )
            else:
                title_en = existing_row[3] if existing_row else None
                description_en = existing_row[4] if existing_row and len(existing_row) > 4 else None
                location_name_en = existing_row[5] if existing_row and len(existing_row) > 5 else None

            if existing_row:
                event_id = existing_row[0]
                conn.execute(
                    text("""
                    UPDATE events
                    SET title = :title, title_en = :title_en,
                        description = :description, description_en = :description_en,
                        location_name = :location_name, location_name_en = :location_name_en,
                        starts_at = :starts_at, ends_at = :ends_at, city = :city, lat = :lat, lng = :lng,
                        location_url = :location_url, url = :url, country = :country,
                        place_id = :place_id, event_source = 'parser',
                        community_name = COALESCE(:community_name, community_name),
                        community_link = COALESCE(:community_link, community_link),
                        chat_id = COALESCE(:chat_id, chat_id),
                        organizer_username = COALESCE(:organizer_username, organizer_username),
                        referral_code = COALESCE(:referral_code, referral_code),
                        updated_at_utc = NOW()
                    WHERE source = :source AND external_id = :external_id
                """),
                    {
                        "title": title,
                        "title_en": title_en,
                        "description": description,
                        "description_en": description_en,
                        "location_name": location_name,
                        "location_name_en": location_name_en,
                        "starts_at": starts_at_utc,
                        "ends_at": ends_at_utc,
                        "city": city,
                        "lat": lat,
                        "lng": lng,
                        "location_url": location_url,
                        "url": url,
                        "country": country,
                        "place_id": place_id,
                        "community_name": community_name,
                        "community_link": community_link,
                        "chat_id": chat_id,
                        "organizer_username": organizer_username,
                        "referral_code": referral_code,
                        "source": source,
                        "external_id": external_id,
                    },
                )
                print(f"🔄 Обновлено парсерное событие ID {event_id}: '{title}'")
            else:
                result = conn.execute(
                    text("""
                    INSERT INTO events
                    (source, external_id, event_source, title, title_en, description, description_en,
                     starts_at, ends_at, city, lat, lng, location_name, location_name_en,
                     location_url, url, country, is_generated_by_ai, status,
                     current_participants, place_id, community_name, community_link,
                     chat_id, organizer_username, referral_code)
                    VALUES
                    (:source, :external_id, 'parser', :title, :title_en, :description, :description_en,
                     :starts_at, :ends_at, :city, :lat, :lng, :location_name, :location_name_en,
                     :location_url, :url, :country, :is_ai, :status, 0, :place_id,
                     :community_name, :community_link, :chat_id, :organizer_username, :referral_code)
                    ON CONFLICT (source, external_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        title_en = EXCLUDED.title_en,
                        description = EXCLUDED.description,
                        description_en = EXCLUDED.description_en,
                        location_name = EXCLUDED.location_name,
                        location_name_en = EXCLUDED.location_name_en,
                        event_source = 'parser',
                        starts_at = EXCLUDED.starts_at,
                        ends_at = EXCLUDED.ends_at,
                        city = EXCLUDED.city,
                        lat = EXCLUDED.lat,
                        lng = EXCLUDED.lng,
                        location_url = EXCLUDED.location_url,
                        url = EXCLUDED.url,
                        country = EXCLUDED.country,
                        place_id = EXCLUDED.place_id,
                        community_name = COALESCE(EXCLUDED.community_name, events.community_name),
                        community_link = COALESCE(EXCLUDED.community_link, events.community_link),
                        chat_id = COALESCE(EXCLUDED.chat_id, events.chat_id),
                        organizer_username = COALESCE(EXCLUDED.organizer_username, events.organizer_username),
                        referral_code = COALESCE(EXCLUDED.referral_code, events.referral_code)
                    RETURNING id
                """),
                    {
                        "source": source,
                        "external_id": external_id,
                        "title": title,
                        "title_en": title_en,
                        "description": description,
                        "description_en": description_en,
                        "starts_at": starts_at_utc,
                        "ends_at": ends_at_utc,
                        "city": city,
                        "lat": lat,
                        "lng": lng,
                        "location_name": location_name,
                        "location_name_en": location_name_en,
                        "location_url": location_url,
                        "url": url,
                        "country": country,
                        "is_ai": is_ai,
                        "status": status,
                        "place_id": place_id,
                        "community_name": community_name,
                        "community_link": community_link,
                        "chat_id": chat_id,
                        "organizer_username": organizer_username,
                        "referral_code": referral_code,
                    },
                )
                event_id = result.fetchone()[0]
                print(f"✅ Создано парсерное событие ID {event_id}: '{title}'")

        return event_id

    def cleanup_old_events(self, city: str) -> int:
        """Очистка старых событий из единой таблицы events

        ВАЖНО: В архив попадают ТОЛЬКО пользовательские события (source = 'user').
        События от парсеров (baliforum, kudago, ai) просто удаляются без архивации.
        """
        with self.engine.begin() as conn:
            # Переносим устаревшие записи в архив ТОЛЬКО для пользовательских событий
            # Для открытых событий: по дате начала (starts_at)
            # Для закрытых событий: по времени закрытия (updated_at_utc),
            # чтобы можно было возобновить в течение 24 часов
            archived_count = conn.execute(
                text(
                    """
                    INSERT INTO events_archive (
                        id, source, external_id, title, description,
                        time_local, date_local, city, country, venue, address,
                        lat, lng, url, price, organizer_id, organizer_username,
                        created_at_utc, updated_at_utc, archived_at_utc
                    )
                    SELECT
                        id, source, external_id, title, description,
                        NULL, NULL, city, country,
                        location_name, location_name,
                        lat, lng, url, NULL, organizer_id, organizer_username,
                        created_at_utc, updated_at_utc, NOW()
                    FROM events
                    WHERE city = :city
                    AND source = 'user'
                    AND (
                        -- Открытые события: архивируем по дате начала
                        (status = 'open' AND starts_at < NOW() - INTERVAL '1 day')
                        OR
                        -- Закрытые события: архивируем только если закрыты более 24 часов назад
                        (status = 'closed' AND updated_at_utc < NOW() - INTERVAL '24 hours')
                    )
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"city": city},
            ).rowcount

            # Удаляем все старые события (и пользовательские, и парсерные)
            # Для парсерных событий: по дате начала (как раньше)
            # Для пользовательских: по той же логике, что и архивация
            events_deleted = conn.execute(
                text(
                    """
                    DELETE FROM events
                    WHERE city = :city
                    AND (
                        -- Парсерные события: удаляем по дате начала (как раньше)
                        (source != 'user' AND starts_at < NOW() - INTERVAL '1 day')
                        OR
                        -- Пользовательские открытые события: удаляем по дате начала
                        (source = 'user' AND status = 'open' AND starts_at < NOW() - INTERVAL '1 day')
                        OR
                        -- Пользовательские закрытые события: удаляем только если закрыты более 24 часов назад
                        (source = 'user' AND status = 'closed' AND updated_at_utc < NOW() - INTERVAL '24 hours')
                    )
                    """
                ),
                {"city": city},
            ).rowcount

            print(
                f"🧹 Очистка {city}: заархивировано {archived_count} пользовательских событий, "
                f"удалено {events_deleted} событий (включая парсерные) из единой таблицы events"
            )

            return events_deleted
