from __future__ import annotations

import hashlib
from typing import Any

from openai import OpenAI

from config import load_settings


def _make_client() -> OpenAI | None:
    settings = load_settings()
    if not settings.openai_api_key:
        return None

    # Поддержка как User API Key, так и Project API Key
    api_key = settings.openai_api_key

    # Для Project API Key нужно указать organization
    if api_key.startswith("sk-proj-") and settings.openai_organization:
        # Project API Key - используем organization
        return OpenAI(api_key=api_key, organization=settings.openai_organization)
    else:
        # Обычный User API Key или Project Key без organization
        return OpenAI(api_key=api_key)


def _dedupe_key(title: str, time_utc_iso: str, lat: float, lng: float) -> str:
    raw = f"{title}|{time_utc_iso}|{lat:.6f}|{lng:.6f}".encode()
    return hashlib.sha1(raw).hexdigest()


async def fetch_ai_events_nearby(lat: float, lng: float) -> list[dict[str, Any]]:
    """
    Query GPT for events near given coordinates and return normalized list.

    Expected item fields per entry:
    - title (str)
    - description (str?)
    - time_local (str, "YYYY-MM-DD HH:MM")
    - tz (str IANA?) optional; can be derived elsewhere
    - location_name (str?)
    - location_url (str?)
    - lat (float), lng (float)
    - community_name (str?)
    - community_link (str?)
    """
    import logging

    logger = logging.getLogger(__name__)

    client = _make_client()
    if client is None:
        logger.warning("⚠️ OpenAI API ключ не настроен, пропускаем AI поиск")
        return []

    prompt = (
        "Ты помощник для парсинга реальных событий из существующих источников. "
        "НЕ ПРИДУМЫВАЙ события! Только парси реальные события из известных источников. "
        "Если нет реальных событий - верни пустой массив []. "
        "Каждый объект должен иметь ВАЛИДНЫЙ URL источника: "
        "{title, description, time_local, location_name, location_url, lat, lng, community_name, community_link}. "
        f"Координаты: lat={lat:.6f}, lng={lng:.6f}. Время локальное формата 'YYYY-MM-DD HH:MM'. "
        "ВАЖНО: location_url должен быть реальным URL существующего источника, НЕ example.com!"
    )

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Return ONLY valid JSON array."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            timeout=15,  # Добавляем timeout
        )
        logger.info("✅ AI вернул ответ успешно")
    except Exception as e:
        logger.warning(f"⚠️ Ошибка при генерации AI: {e}. Fallback → пустой список.")
        return []

    content = completion.choices[0].message.content or "[]"
    # Lazy import to avoid heavyweight dep if unused
    import json

    try:
        data = json.loads(content)
        if not isinstance(data, list):
            return []
    except Exception:
        return []

    normalized: list[dict[str, Any]] = []
    for item in data:
        try:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            time_local = str(item.get("time_local") or "").strip()
            lat_i = float(item.get("lat")) if item.get("lat") is not None else None
            lng_i = float(item.get("lng")) if item.get("lng") is not None else None
            if lat_i is None or lng_i is None:
                continue

            # Валидация URL - отфильтровываем фейковые ссылки
            location_url = item.get("location_url") or ""
            if location_url:
                # Проверяем, что это не фейковая ссылка
                if any(
                    fake in location_url.lower()
                    for fake in [
                        "example.com",
                        "example.org",
                        "example.net",
                        "test.com",
                        "demo.com",
                    ]
                ):
                    logger.warning(f"⚠️ Отфильтрован фейковый URL: {location_url}")
                    continue

            normalized.append(
                {
                    "title": title[:120],
                    "description": (item.get("description") or "")[:500],
                    "time_local": time_local[:16],
                    "location_name": (item.get("location_name") or "")[:255],
                    "location_url": item.get("location_url") or "",
                    "lat": lat_i,
                    "lng": lng_i,
                    "community_name": (item.get("community_name") or "")[:120],
                    "community_link": item.get("community_link") or "",
                }
            )
        except Exception:
            continue

    return normalized
