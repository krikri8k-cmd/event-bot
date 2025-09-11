# sources/baliforum.py
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
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
}

TIME_RE = re.compile(r"(?P<h>\d{1,2}):(?P<m>\d{2})")
MAP_RE = re.compile(r"/@(?P<lat>-?\d+\.\d+),(?P<lng>-?\d+\.\d+)|query=(?P<lat2>-?\d+\.\d+)%2C(?P<lng2>-?\d+\.\d+)")


def _parse_time(s: str) -> tuple[int, int] | None:
    """Парсит время в формате HH:MM"""
    m = TIME_RE.search(s)
    if not m:
        return None
    return int(m["h"]), int(m["m"])


def _ru_date_to_dt(label: str, now: datetime, tz: ZoneInfo) -> tuple[datetime | None, datetime | None]:
    """
    Принимает строки вида:
    'Сегодня с 09:00 до 21:00', 'Завтра с 18:00', '8 сент., с 20:00 до 01:00', 'Сегодня весь день'
    Возвращает (start_dt, end_dt) в tz.
    """
    try:
        label = label.strip().lower()
        day = None

        if label.startswith("сегодня"):
            day = now.date()
            label.replace("сегодня", "").strip()
        elif label.startswith("завтра"):
            day = (now + timedelta(days=1)).date()
            label.replace("завтра", "").strip()
        else:
            # '8 сент., с 20:00 до 01:00' / '8 сентября'
            parts = label.split(",")[0].split()
            if len(parts) >= 2:
                d = int(re.sub(r"[^\d]", "", parts[0]))
                mon = RU_MONTHS.get(parts[1][:3], None)
                if mon:
                    year = now.year
                    day = datetime(year, mon, d, tzinfo=tz).date()
            label[label.find(",") + 1 :] if "," in label else ""

        start_dt = end_dt = None

        if day:
            if "весь день" in label:
                start_dt = datetime.combine(day, datetime.min.time(), tz)
                end_dt = start_dt + timedelta(hours=23, minutes=59)
            else:
                # 'с 09:00 до 21:00' / 'с 19:00'
                if "с " in label:
                    t1 = _parse_time(label.split("с", 1)[1])
                    if t1:
                        start_dt = datetime(day.year, day.month, day.day, t1[0], t1[1], tzinfo=tz)

                if "до " in label:
                    t2 = _parse_time(label.split("до", 1)[1])
                    if t2 and start_dt:
                        # поддержка «до 01:00» на следующий день
                        end_dt = datetime(day.year, day.month, day.day, t2[0], t2[1], tzinfo=tz)
                        if end_dt <= start_dt:
                            end_dt += timedelta(days=1)

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
    html = _fetch(LIST_URL)
    soup = BeautifulSoup(html, "html.parser")

    # Ищем карточки событий
    cards = soup.select("div.event-card, article.event") or soup.select("li.event-item")
    events: list[dict] = []

    for card in cards[:limit]:
        a = card.select_one("a")
        if not a or not a.get("href"):
            continue

        url = a["href"]
        if url.startswith("/"):
            url = BASE + url

        title = (a.get_text(strip=True) or "").strip()
        date_text = (
            (card.select_one(".date, time") or {}).get_text(strip=True) if card.select_one(".date, time") else ""
        )

        # Парсим дату
        tz = ZoneInfo("Asia/Makassar")
        now = datetime.now(tz)
        start, end = _ru_date_to_dt(date_text, now, tz)

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

        events.append(
            {
                "source": "baliforum",
                "title": title or "Событие",
                "start_time": start.isoformat() if start else None,
                "end_time": end.isoformat() if end else None,
                "venue": venue,
                "address": venue,  # пусть address=venue для начала
                "lat": lat,
                "lng": lng,
                "url": url,
                "source_url": url,
                "booking_url": None,
                "ticket_url": None,
                "raw": {"date_text": date_text},
            }
        )

        # Rate limiting
        time.sleep(0.3)

    return events


def fetch(limit: int = 100) -> list[RawEvent]:
    """Главная точка входа для инжеста - возвращает RawEvent объекты"""
    events = fetch_baliforum_events(limit)

    # Конвертируем в RawEvent объекты
    raw_events = []
    for event in events:
        # Извлекаем external_id из URL
        external_id = event["url"].rstrip("/").split("/")[-1]

        raw_event = RawEvent(
            external_id=external_id,
            source_name="baliforum",
            title=event["title"],
            start_time=event["start_time"],
            end_time=event["end_time"],
            venue=event["venue"],
            address=event["address"],
            lat=event["lat"],
            lng=event["lng"],
            url=event["url"],
            source_url=event["source_url"],
            booking_url=event["booking_url"],
            ticket_url=event["ticket_url"],
            raw=event["raw"],
            timezone="Asia/Makassar",
        )
        raw_events.append(raw_event)

    return raw_events
