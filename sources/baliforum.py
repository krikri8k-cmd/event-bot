# sources/baliforum.py
from __future__ import annotations

import logging
import re
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from event_apis import RawEvent

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " "AppleWebKit/537.36 (KHTML, like Gecko) " "Chrome/124.0 Safari/537.36"

BASE = "https://baliforum.ru"
LIST_URL = f"{BASE}/events"

RU_MONTHS = {
    "янв": 1,
    "фев": 2,
    "мар": 3,
    "апр": 4,
    "май": 5,
    "мая": 5,
    "июн": 6,
    "июл": 7,
    "авг": 8,
    "сен": 9,
    "сент": 9,
    "окт": 10,
    "ноя": 11,
    "нояб": 11,  # для "нояб." (с точкой)
    "дек": 12,
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
    # Сокращения с точкой (убираем точку при парсинге, но добавляем для полноты)
    "янв.": 1,
    "фев.": 2,
    "мар.": 3,
    "апр.": 4,
    "май.": 5,
    "июн.": 6,
    "июл.": 7,
    "авг.": 8,
    "сен.": 9,
    "сент.": 9,
    "окт.": 10,
    "нояб.": 11,
    "дек.": 12,
}

TIME_RE = re.compile(r"(?P<h>\d{1,2}):(?P<m>\d{2})")
MAP_RE = re.compile(r"/@(?P<lat>-?\d+\.\d+),(?P<lng>-?\d+\.\d+)|query=(?P<lat2>-?\d+\.\d+)%2C(?P<lng2>-?\d+\.\d+)")


def _parse_time(s: str) -> tuple[int, int] | None:
    """Парсит время в формате HH:MM или диапазон HH:MM-HH:MM (берет начало)"""
    # Сначала ищем диапазон времени
    range_match = re.search(r"(\d{1,2}):(\d{2})[–-](\d{1,2}):(\d{2})", s)
    if range_match:
        # Берем начало диапазона
        return int(range_match.group(1)), int(range_match.group(2))

    # Обычное время
    m = TIME_RE.search(s)
    if not m:
        return None
    return int(m["h"]), int(m["m"])


def _ru_date_to_dt(label: str, now: datetime, tz: ZoneInfo) -> tuple[datetime | None, datetime | None]:
    """
    Принимает строки вида:
    'Сегодня с 09:00 до 21:00', 'Завтра с 18:00', '8 сент., с 20:00 до 01:00', 'Сегодня весь день'
    Возвращает (start_dt, end_dt) в tz.

    ВАЖНО: Если нет точного времени - возвращает None (событие пропускается)
    """
    try:
        label = label.strip().lower()
        original_label = label  # Сохраняем оригинал для парсинга времени
        day = None

        if label.startswith("сегодня"):
            day = now.date()
            label = label.replace("сегодня", "").strip()
        elif label.startswith("завтра"):
            day = (now + timedelta(days=1)).date()
            label = label.replace("завтра", "").strip()
        else:
            # Пробуем разные форматы дат
            day = None

            # 1. '8 сент., с 20:00 до 01:00' / '8 сентября' / '8 нояб., с 11:00'
            parts = label.split(",")[0].split()
            if len(parts) >= 2:
                d = int(re.sub(r"[^\d]", "", parts[0]))
                # Пробуем найти месяц: сначала убираем точку если есть (для "нояб." -> "нояб")
                month_str = parts[1].rstrip(".,").lower()
                # Пробуем разные варианты: полное название, сокращение с точкой, сокращение без точки
                mon = RU_MONTHS.get(month_str, None) or RU_MONTHS.get(month_str[:3], None)
                if mon:
                    year = now.year
                    day = datetime(year, mon, d, tzinfo=tz).date()
                    # Если дата в прошлом, переносим на следующий год
                    if day < now.date():
                        day = datetime(year + 1, mon, d, tzinfo=tz).date()

            # 2. '10.09 в 20:15' или '10.09 20:15' (день.месяц)
            if not day:
                dot_match = re.search(r"(\d{1,2})\.(\d{1,2})", label)
                if dot_match:
                    d = int(dot_match.group(1))
                    mon = int(dot_match.group(2))
                    if 1 <= mon <= 12:
                        year = now.year
                        day = datetime(year, mon, d, tzinfo=tz).date()
                        if day < now.date():
                            day = datetime(year + 1, mon, d, tzinfo=tz).date()
                        # Убираем найденную дату из label для дальнейшего парсинга времени
                        label = re.sub(r"\d{1,2}\.\d{1,2}", "", label).strip()

            # 3. День недели 'чт 19:30'
            if not day:
                weekday_map = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6}
                for wd_name, wd_num in weekday_map.items():
                    if wd_name in label:
                        # Находим ближайший такой день недели в течение следующих 7 дней
                        for i in range(1, 8):
                            future_date = now.date() + timedelta(days=i)
                            if future_date.weekday() == wd_num:
                                day = future_date
                                break
                        break

            label = label[label.find(",") + 1 :] if "," in label else ""

        start_dt = end_dt = None

        # Если день не найден, но есть время - НЕ предполагаем что событие сегодня
        # Это может быть событие на завтра или другую дату, поэтому пропускаем
        if not day:
            # Проверяем, есть ли время в оригинальной строке
            if _parse_time(original_label):
                # НЕ устанавливаем day = now.date() - это может быть событие на завтра
                # Вместо этого возвращаем None, чтобы событие было пропущено
                logger.debug("_ru_date_to_dt: дата не найдена, но есть время, пропуск: %r", original_label)
                return None, None

        if day:
            if "весь день" in label or "весь день" in original_label:
                start_dt = datetime.combine(day, datetime.min.time(), tz)
                end_dt = start_dt + timedelta(hours=23, minutes=59)
            else:
                # Ищем время в разных форматах
                time_found = False

                # 1. 'с 09:00 до 21:00' / 'с 19:00'
                if "с " in label:
                    t1 = _parse_time(label.split("с", 1)[1])
                    if t1:
                        start_dt = datetime(day.year, day.month, day.day, t1[0], t1[1], tzinfo=tz)
                        time_found = True

                # 2. Если не нашли через "с ", ищем время в оригинальной строке
                if not time_found:
                    # Убираем "в " для поиска времени и используем оригинальную строку
                    clean_label = original_label.replace("в ", "").strip()
                    t1 = _parse_time(clean_label)
                    if t1:
                        start_dt = datetime(day.year, day.month, day.day, t1[0], t1[1], tzinfo=tz)
                        time_found = True

                # 3. Ищем время "до" для end_dt
                if "до " in label:
                    t2 = _parse_time(label.split("до", 1)[1])
                    if t2 and start_dt:
                        # поддержка «до 01:00» на следующий день
                        end_dt = datetime(day.year, day.month, day.day, t2[0], t2[1], tzinfo=tz)
                        if end_dt <= start_dt:
                            end_dt += timedelta(days=1)

                # Если нет времени, устанавливаем дефолтное время 12:00
                if not time_found:
                    start_dt = datetime(day.year, day.month, day.day, 12, 0, tzinfo=tz)
                    logger.debug("_ru_date_to_dt: время не найдено, используем 12:00 для %r", label)

        return start_dt, end_dt
    except (ValueError, KeyError):
        return None, None


def _extract_latlng_from_maps(url: str) -> tuple[float | None, float | None, str | None, str | None]:
    """
    Извлекает координаты, название места и ссылку из Google Maps URL

    Returns:
        tuple: (lat, lng, place_name, maps_url) или (None, None, None, None) если не удалось распарсить
    """
    if not url:
        return None, None, None, None

    m = MAP_RE.search(url)
    if not m:
        return None, None, None, None

    # Проверяем оба формата: /@lat,lng и query=lat%2Clng
    lat = m.group("lat") or m.group("lat2")
    lng = m.group("lng") or m.group("lng2")

    if not lat or not lng:
        return None, None, None, None

    lat = float(lat)
    lng = float(lng)

    # Извлекаем название места из URL используя функцию из utils/geo_utils
    place_name = None
    try:
        from utils.geo_utils import extract_place_name_from_url

        place_name = extract_place_name_from_url(url)
        if place_name:
            # Очищаем название от лишних символов
            place_name = place_name.strip().replace("+", " ")
    except Exception:
        pass

    # Нормализуем ссылку (убираем лишние параметры, но сохраняем основную структуру)
    url.split("?")[0] if "?" in url else url
    # Если есть координаты в формате @lat,lng, сохраняем их
    if "@" in url:
        url.split("?")[0] if "?" in url else url

    return lat, lng, place_name, url  # Возвращаем оригинальную ссылку


def _extract_tags_from_card(card) -> list[str]:
    """Теги BaliForum из карточки списка (a.event-types__item)."""
    if not card:
        return []
    tags: list[str] = []
    for link in card.select("a.event-types__item"):
        text = link.get_text(strip=True)
        if text:
            tags.append(text)
    return tags


def _fetch(url: str, timeout=15) -> str:
    """Получает HTML страницу"""
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    return r.text


def fetch_baliforum_events(limit: int = 200, date_filter: str | None = None) -> list[dict]:
    """
    Основная функция парсинга событий с baliforum.ru

    Args:
        limit: Максимальное количество событий
        date_filter: Фильтр по дате в формате "YYYY-MM-DD" (например, "2025-11-08")
                    Если None, парсит главную страницу без фильтра
    """
    import logging

    logging.getLogger(__name__)

    # Формируем URL с фильтром по дате если указан
    if date_filter:
        url = f"{LIST_URL}?dateStart={date_filter}"
        logging.info(f"🌴 Парсим BaliForum с фильтром по дате: {date_filter}")
    else:
        url = LIST_URL
        logging.info("🌴 Парсим BaliForum без фильтра (главная страница)")

    html = _fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    # Ищем карточки событий
    cards = soup.select("div.event-card, article.event") or soup.select("li.event-item")
    events: list[dict] = []

    parsed_count = 0
    skipped_no_time = 0
    errors = 0

    for card in cards[:limit]:
        # Ищем все ссылки в карточке
        links = card.find_all("a", href=True)
        if not links:
            continue

        # Берем первую ссылку с текстом (не пустую)
        a = None
        for link in links:
            if link.get_text(strip=True):
                a = link
                break

        if not a:
            continue

        url = a["href"]
        if url.startswith("/"):
            url = BASE + url

        title = a.get_text(strip=True).strip()
        tags = _extract_tags_from_card(card)

        # Ищем дату в тексте карточки
        date_text = ""
        all_text = card.get_text()

        # Ищем паттерны дат с приоритетом по точности
        import re

        date_patterns = [
            # Точные паттерны с временем (высший приоритет) - ПРИОРИТЕТ "ЗАВТРА" ПЕРЕД "СЕГОДНЯ"
            r"Завтра с \d{1,2}:\d{2}(?: до \d{1,2}:\d{2})?",
            r"Завтра \d{1,2}:\d{2}",
            r"Сегодня с \d{1,2}:\d{2}(?: до \d{1,2}:\d{2})?",
            r"Сегодня \d{1,2}:\d{2}",
            r"\d{1,2} (?:янв|фев|мар|апр|май|июн|июл|авг|сен|окт|ноя|нояб|дек)[а-я]*\.?,? "
            r"с \d{1,2}:\d{2}(?: до \d{1,2}:\d{2})?",
            r"\d{1,2} (?:янв|фев|мар|апр|май|июн|июл|авг|сен|окт|ноя|нояб|дек)[а-я]*\.? \d{1,2}:\d{2}",
            # Диапазоны времени (только если есть контекст дня)
            r"\d{1,2}:\d{2}[–-]\d{1,2}:\d{2}",
        ]

        for pattern in date_patterns:
            match = re.search(pattern, all_text)
            if match:
                date_text = match.group(0)
                logger.debug("baliforum: найден шаблон даты %r -> %r для %r", pattern, date_text, title[:50])
                break

        # Парсим дату
        tz = ZoneInfo("Asia/Makassar")
        now = datetime.now(tz)
        start, end = _ru_date_to_dt(date_text, now, tz)

        # Логируем результат парсинга даты
        if start:
            start_bali = start.astimezone(tz)
            today_bali = now.date()
            tomorrow_bali = (now + timedelta(days=1)).date()
            event_date_bali = start_bali.date()
            if event_date_bali == today_bali:
                date_label = "сегодня"
            elif event_date_bali == tomorrow_bali:
                date_label = "завтра"
            else:
                date_label = f"{event_date_bali}"
            logger.debug(
                "baliforum: проанализирована дата %r -> %s (%s) для %r",
                date_text,
                date_label,
                start_bali,
                title[:50],
            )
        else:
            logger.debug("baliforum: не удалось распарсить дату из %r для %r", date_text, title[:50])

        # Конвертируем в UTC для хранения в БД
        if start:
            start = start.astimezone(UTC)
        if end:
            end = end.astimezone(UTC)

        # Пропускаем события, если вообще не удалось извлечь дату
        if not start:
            logger.debug("baliforum: пропуск (нет даты/времени): url=%s, title=%r", url[:60], title[:50])
            skipped_no_time += 1
            continue

        # Детальная страница
        venue = None
        lat = lng = None
        location_url = None
        place_name_from_maps = None
        try:
            detail = _fetch(url)
            ds = BeautifulSoup(detail, "html.parser")

            # Ищем координаты на детальной странице
            # 1. В ссылках на Google Maps
            location_url = None
            place_name_from_maps = None
            for link in ds.find_all("a", href=True):
                href = link["href"]
                if "google.com/maps" in href or "maps.google.com" in href or "/maps" in href:
                    # Нормализуем относительные ссылки
                    if href.startswith("/"):
                        href = "https://www.google.com" + href
                    elif not href.startswith("http"):
                        href = "https://" + href

                    # Используем parse_google_maps_link для лучшего извлечения данных
                    try:
                        import asyncio

                        from utils.geo_utils import parse_google_maps_link

                        # Выполняем async функцию синхронно
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                # Если loop уже запущен, используем ThreadPoolExecutor
                                import concurrent.futures

                                def run_parse():
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    try:
                                        return loop.run_until_complete(parse_google_maps_link(href))
                                    finally:
                                        loop.close()

                                with concurrent.futures.ThreadPoolExecutor() as executor:
                                    future = executor.submit(run_parse)
                                    maps_data = future.result(timeout=5)
                            else:
                                maps_data = loop.run_until_complete(parse_google_maps_link(href))
                        except RuntimeError:
                            maps_data = asyncio.run(parse_google_maps_link(href))

                        if maps_data and maps_data.get("lat") and maps_data.get("lng"):
                            lat = maps_data["lat"]
                            lng = maps_data["lng"]
                            location_url = maps_data.get("raw_link", href)
                            place_name_from_maps = maps_data.get("name")
                            place_id = maps_data.get("place_id")
                            logger.debug(
                                "baliforum: координаты на детальной: %s, %s для %r, место: %s, place_id: %s",
                                lat,
                                lng,
                                title[:50],
                                place_name_from_maps,
                                place_id,
                            )
                            break
                    except Exception as e:
                        # Fallback на старый метод
                        logger.debug("baliforum: ошибка parse_google_maps_link, используем fallback: %s", e)
                        lat, lng, place_name, maps_url = _extract_latlng_from_maps(href)
                        if lat and lng:
                            location_url = maps_url
                            place_name_from_maps = place_name
                            logger.debug(
                                "baliforum: координаты (fallback): %s, %s для %r, место: %s",
                                lat,
                                lng,
                                title[:50],
                                place_name_from_maps,
                            )
                            break

            # Извлекаем venue из HTML страницы
            v = ds.select_one(".event-venue, .place, .location, .event-meta .place")
            venue = v.get_text(strip=True) if v else None

            # Если venue не найдено, но есть название места из Google Maps, используем его
            if not venue and place_name_from_maps:
                venue = place_name_from_maps

            # 2. В data-атрибутах элементов
            if not lat or not lng:
                for elem in ds.find_all(attrs={"data-lat": True, "data-lng": True}):
                    try:
                        lat = float(elem.get("data-lat"))
                        lng = float(elem.get("data-lng"))
                        logger.debug(
                            "baliforum: координаты в data-атрибутах: %s, %s для %r",
                            lat,
                            lng,
                            title[:50],
                        )
                        break
                    except (ValueError, TypeError):
                        continue

            # 3. В тексте страницы (ищем паттерны координат)
            if not lat or not lng:
                import re

                # Ищем паттерны типа "-8.674763, 115.230137" или "lat: -8.674763, lng: 115.230137"
                coord_patterns = [
                    r"(-?\d+\.\d+),\s*(-?\d+\.\d+)",  # Простые координаты
                    r"lat[itude]?[:\s]+(-?\d+\.\d+).*?lng[itude]?[:\s]+(-?\d+\.\d+)",  # lat: X, lng: Y
                    r"@(-?\d+\.\d+),(-?\d+\.\d+)",  # @lat,lng
                ]
                page_text = ds.get_text()
                for pattern in coord_patterns:
                    match = re.search(pattern, page_text, re.IGNORECASE)
                    if match:
                        try:
                            lat = float(match.group(1))
                            lng = float(match.group(2))
                            # Проверяем что координаты в разумных пределах для Бали
                            if -9.0 <= lat <= -8.0 and 114.0 <= lng <= 116.0:
                                logger.debug(
                                    "baliforum: найдены координаты в тексте: %s, %s для %r", lat, lng, title[:50]
                                )
                                break
                        except (ValueError, IndexError):
                            continue
        except Exception as e:
            logger.debug("baliforum: ошибка при парсинге детальной страницы для %r: %s", title[:50], e)
            ds = None

        # Если координаты не найдены на детальной странице, ищем в карточке
        if not lat or not lng:
            for link in card.find_all("a", href=True):
                href = link["href"]
                if "google.com/maps" in href or "/maps" in href:
                    # Нормализуем относительные ссылки
                    if href.startswith("/"):
                        href = "https://www.google.com" + href
                    elif not href.startswith("http"):
                        href = "https://" + href

                    # Используем parse_google_maps_link для лучшего извлечения данных
                    try:
                        import asyncio

                        from utils.geo_utils import parse_google_maps_link

                        logger.debug("baliforum: пытаемся извлечь координаты из ссылки в карточке: %s", href[:100])

                        # Выполняем async функцию синхронно
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                import concurrent.futures

                                def run_parse():
                                    loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(loop)
                                    try:
                                        return loop.run_until_complete(parse_google_maps_link(href))
                                    finally:
                                        loop.close()

                                with concurrent.futures.ThreadPoolExecutor() as executor:
                                    future = executor.submit(run_parse)
                                    maps_data = future.result(timeout=10)
                            else:
                                maps_data = loop.run_until_complete(parse_google_maps_link(href))
                        except RuntimeError:
                            maps_data = asyncio.run(parse_google_maps_link(href))

                        logger.debug("baliforum: parse_google_maps_link (карточка) вернул: %s", maps_data)

                        if maps_data and maps_data.get("lat") and maps_data.get("lng"):
                            lat = maps_data["lat"]
                            lng = maps_data["lng"]
                            location_url = maps_data.get("raw_link", href)
                            place_name_from_maps = maps_data.get("name")
                            place_id = maps_data.get("place_id")
                            logger.debug(
                                "baliforum: найдены координаты в карточке: %s, %s для %r, место: %s, place_id: %s",
                                lat,
                                lng,
                                title[:50],
                                place_name_from_maps,
                                place_id,
                            )
                            break
                        else:
                            logger.debug(
                                "baliforum: parse_google_maps_link (карточка) не нашел координаты в ссылке: %s",
                                href[:100],
                            )
                    except Exception as e:
                        # Fallback на старый метод
                        logger.debug(
                            "baliforum: ошибка parse_google_maps_link в карточке, fallback: %s: %s",
                            type(e).__name__,
                            e,
                        )
                        lat, lng, place_name, maps_url = _extract_latlng_from_maps(href)
                        if lat and lng:
                            location_url = maps_url
                            place_name_from_maps = place_name
                            logger.debug(
                                "baliforum: найдены координаты в карточке (fallback): %s, %s для %r, место: %s",
                                lat,
                                lng,
                                title[:50],
                                place_name_from_maps,
                            )
                            break
                        else:
                            logger.debug("baliforum: fallback (карточка) не нашел координаты в ссылке: %s", href[:100])

        # Если координаты все еще не найдены, пробуем геокодинг по адресу/venue
        if (not lat or not lng) and venue:
            try:
                import asyncio

                from utils.geo_utils import geocode_address

                # Пробуем геокодинг по venue/address
                address = venue.strip()
                if address and len(address) > 5:  # Минимальная длина адреса
                    # Выполняем async функцию синхронно
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Если loop уже запущен, используем ThreadPoolExecutor
                            import concurrent.futures

                            def run_geocode():
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                try:
                                    return loop.run_until_complete(geocode_address(address, region_bias="bali"))
                                finally:
                                    loop.close()

                            with concurrent.futures.ThreadPoolExecutor() as executor:
                                future = executor.submit(run_geocode)
                                coords = future.result(timeout=10)
                        else:
                            coords = loop.run_until_complete(geocode_address(address, region_bias="bali"))
                    except RuntimeError:
                        coords = asyncio.run(geocode_address(address, region_bias="bali"))

                    if coords:
                        lat, lng = coords
                        logger.debug(
                            "baliforum: координаты через геокодинг адреса %r: %s, %s для %r",
                            address[:50],
                            lat,
                            lng,
                            title[:50],
                        )
            except Exception as e:
                logger.debug("baliforum: ошибка геокодинга для %r: %s", title[:50], e)

        # Создаем стабильный external_id
        import hashlib

        normalized_url = url.split("?")[0].split("#")[0]  # Убираем UTM и якоря
        external_id = hashlib.sha1(f"baliforum|{normalized_url}".encode()).hexdigest()[:16]

        try:
            events.append(
                {
                    "source": "baliforum",
                    "title": title or "Событие",
                    "start_time": start,
                    "end_time": end,
                    "venue": venue,
                    "address": venue,  # пусть address=venue для начала
                    "lat": lat,
                    "lng": lng,
                    "url": url,
                    "source_url": url,
                    "location_url": location_url,  # Сохраняем ссылку Google Maps для маршрута
                    "booking_url": None,
                    "ticket_url": None,
                    "external_id": external_id,
                    "tags": tags,
                    "raw": {
                        "date_text": date_text,
                        "tags": tags,
                        "place_name_from_maps": place_name_from_maps,
                        "place_id": place_id,
                    },
                }
            )
            parsed_count += 1
        except Exception as e:
            logger.error("baliforum: ошибка обработки события %r: %s", title[:50], e)
            errors += 1

        # Rate limiting
        time.sleep(0.3)

    # Логируем сводку
    total_cards = len(cards)
    logger.info(
        "baliforum: найдено карточек=%s, обработано=%s, распарсено=%s, пропущено без времени=%s, ошибок=%s",
        total_cards,
        min(total_cards, limit),
        parsed_count,
        skipped_no_time,
        errors,
    )
    if skipped_no_time > 0:
        logger.warning(
            "baliforum: пропущено %s событий без времени (%.1f%% от обработанных)",
            skipped_no_time,
            skipped_no_time / min(total_cards, limit) * 100 if total_cards else 0,
        )
    return events


def fetch(limit: int = 200) -> list[RawEvent]:
    """Главная точка входа для инжеста - возвращает RawEvent объекты"""
    events = fetch_baliforum_events(limit)

    # Конвертируем в RawEvent объекты
    raw_events = []
    for event in events:
        # Используем стабильный external_id из парсера
        external_id = event.get("external_id", event["url"].rstrip("/").split("/")[-1])

        # Парсим дату если есть
        starts_at = event["start_time"]

        # Формируем description с venue и location_url для передачи в БД
        description_parts = []
        if event.get("description"):
            description_parts.append(event["description"])

        # Добавляем venue в description, если есть
        venue = event.get("venue")
        if venue:
            description_parts.append(f"\n📍 Место: {venue}")

        # Сохраняем location_url и venue в raw для использования при сохранении
        raw_data = {
            "venue": venue,
            "location_url": event.get("location_url"),
            "place_name_from_maps": event.get("raw", {}).get("place_name_from_maps"),
            "place_id": event.get("raw", {}).get("place_id"),
            "tags": event.get("tags") or event.get("raw", {}).get("tags") or [],
        }

        raw_event = RawEvent(
            title=event["title"],
            lat=event["lat"] or 0.0,
            lng=event["lng"] or 0.0,
            starts_at=starts_at,
            source="baliforum",
            external_id=external_id,
            url=event["url"],
            description="\n".join(description_parts) if description_parts else None,
        )
        # Сохраняем дополнительные данные в атрибуте raw_event для использования при сохранении
        raw_event._raw_data = raw_data  # type: ignore
        raw_events.append(raw_event)

    return raw_events
