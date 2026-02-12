"""
Перевод полей события (title, description, location_name) с русского на английский
для отображения в боте при выборе языка EN. Использует gpt-4o-mini.
При ошибке API возвращает пустые значения — парсер не должен падать.
Повторные попытки с экспоненциальной задержкой при сетевых сбоях.
Ограничение очереди: семафор (3) — не более 3 запросов к OpenAI одновременно.
"""

import json
import logging
import threading
import time

logger = logging.getLogger(__name__)

# Повторные попытки при сетевых ошибках (ТЗ: до 3 попыток)
MAX_RETRIES = 3
INITIAL_DELAY_SEC = 1.0
MAX_DELAY_SEC = 30.0
OPENAI_TIMEOUT = 20.0  # ТЗ: если за это время ответа нет — оригинал, ошибка в лог

# Модель: в 10 раз дешевле и быстрее, для перевода заголовков достаточно (ТЗ)
OPENAI_MODEL = "gpt-4o-mini"

# Ограничение очереди: не более 3 одновременных запросов к API (ТЗ — убрать Connection Reset)
_sync_semaphore = threading.Semaphore(3)

SYSTEM_PROMPT = (
    "Ты — профессиональный переводчик афиши мероприятий. "
    "Переведи название и текст события на английский язык. Сохраняй смысл и эмоциональный окрас. "
    "Названия заведений и брендов оставляй на латинице. "
    "Если название — имя собственное (игра, практика), можно транслитерация и перевод в скобках, "
    "например: Izobilie (Abundance). Возвращай только валидный JSON без комментариев и пояснений."
)


def _make_client():
    """Синхронный клиент для вызовов из потоков (create_user_event, save_parser_event)."""
    try:
        from openai import OpenAI

        from config import load_settings

        settings = load_settings()
        if not settings.openai_api_key:
            return None
        api_key = settings.openai_api_key
        if api_key.startswith("sk-proj-") and settings.openai_organization:
            return OpenAI(api_key=api_key, organization=settings.openai_organization)
        return OpenAI(api_key=api_key)
    except Exception as e:
        logger.warning("event_translation: не удалось создать OpenAI client: %s", e)
        return None


def _make_async_client():
    """Асинхронный клиент — не блокирует event loop бота при вызове из async-кода."""
    try:
        from openai import AsyncOpenAI

        from config import load_settings

        settings = load_settings()
        if not settings.openai_api_key:
            return None
        api_key = settings.openai_api_key
        if api_key.startswith("sk-proj-") and settings.openai_organization:
            return AsyncOpenAI(api_key=api_key, organization=settings.openai_organization)
        return AsyncOpenAI(api_key=api_key)
    except Exception as e:
        logger.warning("event_translation: не удалось создать AsyncOpenAI client: %s", e)
        return None


def translate_event_to_english(
    title: str,
    description: str | None = None,
    location_name: str | None = None,
) -> dict[str, str | None]:
    """
    Переводит title, description, location_name с русского на английский.
    Возвращает {"title_en": ..., "description_en": ..., "location_name_en": ...}.
    При любой ошибке возвращает пустые значения (None) для полей перевода.
    """
    result: dict[str, str | None] = {
        "title_en": None,
        "description_en": None,
        "location_name_en": None,
    }
    title = (title or "").strip()
    if not title:
        return result

    client = _make_client()
    if not client:
        logger.debug("event_translation: OpenAI ключ не настроен, пропускаем перевод")
        return result

    # Собираем поля для перевода (пропускаем пустые)
    parts = [f"title: {title}"]
    if description and (description or "").strip():
        parts.append(f"description: {(description or '').strip()}")
    if location_name and (location_name or "").strip():
        parts.append(f"location_name: {(location_name or '').strip()}")

    user_content = "\n\n".join(parts)
    if user_content.strip() == "title: ":
        return result

    format_instruction = (
        ' Формат ответа: {"title_en": "...", "description_en": "...", '
        '"location_name_en": "..."}. Пустые поля — пустая строка или null.'
    )
    _sync_semaphore.acquire()
    try:
        for attempt in range(MAX_RETRIES):
            try:
                completion = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT + format_instruction},
                        {"role": "user", "content": "Переведи на английский и верни JSON:\n\n" + user_content},
                    ],
                    temperature=0.3,
                    timeout=OPENAI_TIMEOUT,
                )
                raw = (completion.choices[0].message.content or "").strip()
                if not raw:
                    return result
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()
                data = json.loads(raw)
                result["title_en"] = (data.get("title_en") or "").strip() or None
                result["description_en"] = (data.get("description_en") or "").strip() or None
                result["location_name_en"] = (data.get("location_name_en") or "").strip() or None
                if result["title_en"]:
                    logger.debug(
                        "event_translation: переведено title %r -> %r",
                        title[:50],
                        (result["title_en"] or "")[:50],
                    )
                return result
            except json.JSONDecodeError as e:
                logger.warning("event_translation: невалидный JSON от GPT: %s", e)
                return result
            except Exception as e:
                # Явный retry при APIConnectionError и таймаутах (ТЗ: до 3 попыток)
                is_connection_error = "APIConnectionError" in type(e).__name__ or "connection" in str(e).lower()
                is_timeout = "timeout" in str(e).lower()
                is_retryable = (
                    is_connection_error or is_timeout or "network" in str(e).lower() or "reset" in str(e).lower()
                ) and (attempt < MAX_RETRIES - 1)
                if is_retryable:
                    delay = min(INITIAL_DELAY_SEC * (2**attempt), MAX_DELAY_SEC)
                    logger.warning(
                        "event_translation: попытка %s/%s ошибка (%s), повтор через %.1f с",
                        attempt + 1,
                        MAX_RETRIES,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.warning(
                        "event_translation: ошибка перевода (оставляем _en пустыми, выводим оригинал): %s",
                        e,
                    )
                    return result
        return result
    finally:
        _sync_semaphore.release()


# Семафор для async: создаётся при первом вызове в async-контексте
_async_semaphore = None


async def translate_event_to_english_async(
    title: str,
    description: str | None = None,
    location_name: str | None = None,
) -> dict[str, str | None]:
    """
    Асинхронный перевод (AsyncOpenAI). Использовать из async-кода, чтобы не блокировать поток бота.
    До 3 попыток при APIConnectionError/timeout, timeout=20 с. Не более 3 запросов одновременно (семафор).
    """
    import asyncio

    global _async_semaphore
    if _async_semaphore is None:
        _async_semaphore = asyncio.Semaphore(3)

    result: dict[str, str | None] = {
        "title_en": None,
        "description_en": None,
        "location_name_en": None,
    }
    title = (title or "").strip()
    if not title:
        return result

    client = _make_async_client()
    if not client:
        return result

    parts = [f"title: {title}"]
    if description and (description or "").strip():
        parts.append(f"description: {(description or '').strip()}")
    if location_name and (location_name or "").strip():
        parts.append(f"location_name: {(location_name or '').strip()}")
    user_content = "\n\n".join(parts)
    if user_content.strip() == "title: ":
        return result

    format_instruction = (
        ' Формат ответа: {"title_en": "...", "description_en": "...", '
        '"location_name_en": "..."}. Пустые поля — пустая строка или null.'
    )
    async with _async_semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                completion = await client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT + format_instruction},
                        {"role": "user", "content": "Переведи на английский и верни JSON:\n\n" + user_content},
                    ],
                    temperature=0.3,
                    timeout=OPENAI_TIMEOUT,
                )
                raw = (completion.choices[0].message.content or "").strip()
                if not raw:
                    return result
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()
                data = json.loads(raw)
                result["title_en"] = (data.get("title_en") or "").strip() or None
                result["description_en"] = (data.get("description_en") or "").strip() or None
                result["location_name_en"] = (data.get("location_name_en") or "").strip() or None
                return result
            except json.JSONDecodeError:
                return result
            except Exception as e:
                is_retryable = (
                    "connection" in str(e).lower() or "timeout" in str(e).lower()
                ) and attempt < MAX_RETRIES - 1
                if is_retryable:
                    delay = min(INITIAL_DELAY_SEC * (2**attempt), MAX_DELAY_SEC)
                    logger.warning(
                        "event_translation (async): попытка %s/%s ошибка (%s), повтор через %.1f с",
                        attempt + 1,
                        MAX_RETRIES,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning("event_translation (async): ошибка перевода: %s", e)
                    return result
        return result


# Промпт для пакетного перевода только заголовков (ТЗ: один вызов — список строк)
BATCH_SYSTEM_PROMPT = (
    "Ты — профессиональный переводчик афиши мероприятий. "
    "Переведи список названий событий на английский. Сохраняй смысл и порядок. "
    "Верни только JSON-массив строк в том же порядке, без комментариев. "
    'Пример: ["Title 1", "Title 2"].'
)


def translate_titles_batch(titles: list[str]) -> list[str | None]:
    """
    Переводит список заголовков одним запросом к OpenAI. Возвращает список той же длины;
    на месте ошибки или пустого ответа — None (в БД не записывать, оставить NULL для повтора).
    """
    if not titles:
        return []
    titles = [(t or "").strip() for t in titles]
    if all(not t for t in titles):
        return [None] * len(titles)

    client = _make_client()
    if not client:
        return [None] * len(titles)

    # Нумеруем, чтобы сохранить порядок при пустых/дублях
    numbered = [f"{i + 1}. {t}" for i, t in enumerate(titles) if t]
    if not numbered:
        return [None] * len(titles)
    user_content = "Переведи на английский и верни JSON-массив строк в том же порядке:\n\n" + "\n".join(numbered)

    _sync_semaphore.acquire()
    try:
        for attempt in range(MAX_RETRIES):
            try:
                completion = client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0.3,
                    timeout=OPENAI_TIMEOUT,
                )
                raw = (completion.choices[0].message.content or "").strip()
                if not raw:
                    return [None] * len(titles)
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()
                data = json.loads(raw)
                if not isinstance(data, list):
                    logger.warning("event_translation batch: ответ не массив: %s", type(data))
                    return [None] * len(titles)
                # Сопоставляем по индексу (модель должна вернуть столько же элементов)
                result = [None] * len(titles)
                non_empty_idx = 0
                for i, t in enumerate(titles):
                    if not t:
                        continue
                    if non_empty_idx < len(data):
                        val = data[non_empty_idx]
                        result[i] = (str(val).strip() or None) if val else None
                    non_empty_idx += 1
                logger.debug("event_translation batch: переведено %s из %s", sum(1 for r in result if r), len(titles))
                return result
            except json.JSONDecodeError as e:
                logger.warning("event_translation batch: невалидный JSON: %s", e)
                return [None] * len(titles)
            except Exception as e:
                is_retryable = (
                    "connection" in str(e).lower() or "timeout" in str(e).lower()
                ) and attempt < MAX_RETRIES - 1
                if is_retryable:
                    delay = min(INITIAL_DELAY_SEC * (2**attempt), MAX_DELAY_SEC)
                    logger.warning(
                        "event_translation batch: попытка %s/%s ошибка (%s), повтор через %.1f с",
                        attempt + 1,
                        MAX_RETRIES,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.warning("event_translation batch: ошибка (оставляем NULL для повтора): %s", e)
                    return [None] * len(titles)
        return [None] * len(titles)
    finally:
        _sync_semaphore.release()


async def translate_titles_batch_async(titles: list[str]) -> list[str | None]:
    """Асинхронный пакетный перевод заголовков. Семафор общий с одиночным async-переводом."""
    import asyncio

    global _async_semaphore
    if _async_semaphore is None:
        _async_semaphore = asyncio.Semaphore(3)

    if not titles:
        return []
    titles = [(t or "").strip() for t in titles]
    if all(not t for t in titles):
        return [None] * len(titles)

    client = _make_async_client()
    if not client:
        return [None] * len(titles)

    numbered = [f"{i + 1}. {t}" for i, t in enumerate(titles) if t]
    if not numbered:
        return [None] * len(titles)
    user_content = "Переведи на английский и верни JSON-массив строк в том же порядке:\n\n" + "\n".join(numbered)

    async with _async_semaphore:
        for attempt in range(MAX_RETRIES):
            try:
                completion = await client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": BATCH_SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=0.3,
                    timeout=OPENAI_TIMEOUT,
                )
                raw = (completion.choices[0].message.content or "").strip()
                if not raw:
                    return [None] * len(titles)
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()
                data = json.loads(raw)
                if not isinstance(data, list):
                    return [None] * len(titles)
                result = [None] * len(titles)
                non_empty_idx = 0
                for i, t in enumerate(titles):
                    if not t:
                        continue
                    if non_empty_idx < len(data):
                        val = data[non_empty_idx]
                        result[i] = (str(val).strip() or None) if val else None
                    non_empty_idx += 1
                return result
            except json.JSONDecodeError as e:
                logger.warning("event_translation batch (async): невалидный JSON: %s", e)
                return [None] * len(titles)
            except Exception as e:
                is_retryable = (
                    "connection" in str(e).lower() or "timeout" in str(e).lower()
                ) and attempt < MAX_RETRIES - 1
                if is_retryable:
                    delay = min(INITIAL_DELAY_SEC * (2**attempt), MAX_DELAY_SEC)
                    logger.warning(
                        "event_translation batch (async): попытка %s/%s ошибка (%s), повтор через %.1f с",
                        attempt + 1,
                        MAX_RETRIES,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning(
                        "event_translation batch (async): ошибка (оставляем NULL для повтора): %s",
                        e,
                    )
                    return [None] * len(titles)
        return [None] * len(titles)
