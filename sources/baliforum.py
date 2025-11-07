# sources/baliforum.py
from __future__ import annotations

import re
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from event_apis import RawEvent

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
                print(f"DEBUG: _ru_date_to_dt: no date found but time exists, skipping: '{original_label}'")
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
                    print(f"DEBUG: _ru_date_to_dt: no time found, using 12:00 for '{label}'")

        return start_dt, end_dt
    except (ValueError, KeyError):
        return None, None


def _extract_latlng_from_maps(url: str) -> tuple[float | None, float | None]:
    """Извлекает координаты из Google Maps URL"""
    m = MAP_RE.search(url or "")
    if not m:
        return None, None

    # Проверяем оба формата: /@lat,lng и query=lat%2Clng
    lat = m.group("lat") or m.group("lat2")
    lng = m.group("lng") or m.group("lng2")

    if lat and lng:
        return float(lat), float(lng)
    return None, None


def _fetch(url: str, timeout=15) -> str:
    """Получает HTML страницу"""
    r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    r.raise_for_status()
    return r.text


def fetch_baliforum_events(limit: int = 100) -> list[dict]:
    """Основная функция парсинга событий с baliforum.ru"""
    import logging

    logging.getLogger(__name__)

    html = _fetch(LIST_URL)
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
                print(f"DEBUG: baliforum: found date pattern '{pattern}' -> '{date_text}' for '{title}'")
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
            print(f"DEBUG: baliforum: parsed date '{date_text}' -> {date_label} ({start_bali}) for '{title}'")
        else:
            print(f"DEBUG: baliforum: failed to parse date from '{date_text}' for '{title}'")

        # Конвертируем в UTC для хранения в БД
        if start:
            start = start.astimezone(UTC)
        if end:
            end = end.astimezone(UTC)

        # Пропускаем события, если вообще не удалось извлечь дату
        if not start:
            print(f"DEBUG: baliforum: skip (no date/time): url={url}, title={title}, date_text='{date_text}'")
            skipped_no_time += 1
            continue

        # Детальная страница
        venue = None
        try:
            detail = _fetch(url)
            ds = BeautifulSoup(detail, "html.parser")
            v = ds.select_one(".event-venue, .place, .location, .event-meta .place")
            venue = v.get_text(strip=True) if v else None
        except Exception:
            ds = None

        # Извлекаем координаты из ссылок на карты
        lat = lng = None
        for link in card.find_all("a", href=True):
            href = link["href"]
            if "google.com/maps" in href or "/maps" in href:
                lat, lng = _extract_latlng_from_maps(href)
                if lat and lng:
                    break

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
                    "booking_url": None,
                    "ticket_url": None,
                    "external_id": external_id,
                    "raw": {"date_text": date_text},
                }
            )
            parsed_count += 1
        except Exception as e:
            print(f"ERROR: baliforum: error processing event '{title}': {e}")
            errors += 1

        # Rate limiting
        time.sleep(0.3)

    # Логируем сводку
    print(f"INFO baliforum: parsed={parsed_count}, skipped_no_time={skipped_no_time}, errors={errors}")
    return events


def fetch(limit: int = 100) -> list[RawEvent]:
    """Главная точка входа для инжеста - возвращает RawEvent объекты"""
    events = fetch_baliforum_events(limit)

    # Конвертируем в RawEvent объекты
    raw_events = []
    for event in events:
        # Используем стабильный external_id из парсера
        external_id = event.get("external_id", event["url"].rstrip("/").split("/")[-1])

        # Парсим дату если есть
        starts_at = event["start_time"]

        raw_event = RawEvent(
            title=event["title"],
            lat=event["lat"] or 0.0,
            lng=event["lng"] or 0.0,
            starts_at=starts_at,
            source="baliforum",
            external_id=external_id,
            url=event["url"],
            description=event.get("description"),
        )
        raw_events.append(raw_event)

    return raw_events
