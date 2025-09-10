# venue_enrich.py
import re

VENUE_RX = re.compile(
    r"(?:в|у|at|in)\s+(?P<name>[A-Za-zА-Яа-я0-9&''-\.]+(?:\s+[A-Za-zА-Яа-я0-9&''-\.]+)*?)(?:\s+на\s+|\s+at\s+|\s+в\s+|\s+у\s+|$)",
    re.IGNORECASE,
)
ADDRESS_HINTS = ["ул.", "улица", "Jl.", "Jalan", "str.", "street", "пл.", "бульвар", "boulevard"]


def extract_coords(text: str) -> tuple[float, float] | None:
    """Извлекает координаты из текста"""
    m = re.search(r"(-?\d{1,2}\.\d{3,})\s*[,; ]\s*(-?\d{1,3}\.\d{3,})", text)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return (lat, lon)
    return None


def extract_address_by_hints(text: str) -> str | None:
    """Извлекает адрес по подсказкам"""
    lowered = text.lower()
    if any(h in lowered for h in (h.lower() for h in ADDRESS_HINTS)):
        # простая эвристика — первая строка/фраза до 120 символов
        seg = text.strip().split("\n")[0]
        return seg[:120]
    return None


def is_plausible_venue(name: str) -> bool:
    """Проверяет, является ли название места правдоподобным"""
    s = name.strip().lower()
    if len(s.replace(" ", "")) < 3:
        return False
    return not s.startswith(("место", "location", "venue"))


def enrich_venue_from_text(event: dict) -> dict:
    """Обогащает событие информацией о локации из текста"""
    # Проверяем каждое поле отдельно
    fields_to_check = [
        event.get("raw_description"),
        event.get("raw_location"),
        event.get("description"),
        event.get("title"),
    ]

    for text in fields_to_check:
        if not text:
            continue

        # 1) Координаты (если они в тексте)
        if not event.get("coords") and not (event.get("lat") and event.get("lng")):
            if c := extract_coords(text):
                event["coords"] = c
                event["lat"] = c[0]
                event["lng"] = c[1]

        # 2) Адрес по эвристикам
        if not event.get("address"):
            if addr := extract_address_by_hints(text):
                event["address"] = addr

        # 3) Название площадки по VENUE_RX (если явно встречается)
        if not event.get("venue_name"):
            m = VENUE_RX.search(text)
            if m:
                name = m.group("name").strip(" ,–—")
                if is_plausible_venue(name):
                    event["venue_name"] = name
                    break  # Нашли название места, больше не ищем

    # 4) Геокодирование: если есть address/venue, но нет coords
    if not event.get("coords") and (event.get("address") or event.get("venue_name")):
        try:
            from geocode import geocode_best_effort

            latlng = geocode_best_effort(event.get("venue_name"), event.get("address"))
            if latlng:
                event["coords"] = latlng
                event["lat"] = latlng[0]
                event["lng"] = latlng[1]
        except ImportError:
            pass  # Геокодер не установлен

    # 5) Реверс-геокодирование: если есть coords, но нет адреса/имени
    if event.get("coords") and not (event.get("address") or event.get("venue_name")):
        try:
            from geocode import reverse_geocode_best_effort

            lat, lon = event["coords"]
            if addr := reverse_geocode_best_effort(lat, lon):
                event["address"] = addr
        except ImportError:
            pass  # Геокодер не установлен

    return event
