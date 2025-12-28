#!/usr/bin/env python3
"""
AI генерация подсказок (task_hint) для мест
"""

import logging

from ai_utils import _make_client

logger = logging.getLogger(__name__)


def generate_task_hint(place_name: str, category: str, place_type: str, description: str | None = None) -> str | None:
    """
    Генерирует короткую подсказку для места с помощью AI

    Args:
        place_name: Название места
        category: Категория ('food', 'health', 'places')
        place_type: Тип места ('cafe', 'gym', 'park', etc.)
        description: Описание места (опционально)

    Returns:
        Короткая подсказка (1 предложение, до 200 символов) или None при ошибке
    """
    client = _make_client()
    if not client:
        logger.warning("OpenAI API ключ не настроен, пропускаем генерацию подсказки")
        return None

    # Маппинг категорий на понятные названия
    category_names = {
        "food": "еда, кафе, рестораны",
        "health": "спорт, здоровье, активность",
        "places": "интересные места, достопримечательности",
    }

    # Маппинг типов мест на понятные названия
    place_type_names = {
        "cafe": "кафе",
        "restaurant": "ресторан",
        "street_food": "уличная еда",
        "market": "рынок",
        "bakery": "пекарня",
        "coworking": "коворкинг-кафе",
        "gym": "спортзал",
        "spa": "спа",
        "lab": "лаборатория",
        "clinic": "клиника",
        "nature": "природа",
        "park": "парк",
        "exhibition": "выставка",
        "temple": "храм",
        "trail": "тропа",
        "beach": "пляж",
        "yoga_studio": "йога-студия",
        "viewpoint": "смотровая площадка",
        "cliff": "утес",
        "beach_club": "пляжный клуб",
        "culture": "культура",
    }

    category_hint = category_names.get(category, category)
    place_type_hint = place_type_names.get(place_type, place_type)

    # Формируем промпт
    prompt = f"""Создай короткую, интересную подсказку (1 предложение, до 200 символов) для места.

Место: {place_name}
Категория: {category_hint}
Тип: {place_type_hint}
{f'Описание: {description}' if description else ''}

Подсказка должна быть:
- Короткой (1 предложение, максимум 200 символов)
- Интересной и мотивирующей
- Конкретной (что именно делать)
- В дружелюбном тоне
- На русском языке
- НЕ упоминать другие заведения или места (только про это место "{place_name}")

Примеры хороших подсказок:
- "Попробуй кофе, поговори с бариста о сортах"
- "Сделай утреннюю пробежку по парку, насладись природой"
- "Посети храм, понаблюдай за архитектурой и атмосферой"
- "Найди предмет декора, который тебя вдохновляет"
- "Попробуй местное блюдо, узнай его историю"

КРИТИЧЕСКИ ВАЖНО:
- Подсказка должна быть про место "{place_name}"
- НЕ упоминай другие заведения или названия мест
- Используй общие слова: "это место", "здесь", "в этом заведении"

ВАЖНО: Ответь ТОЛЬКО подсказкой, без дополнительных слов, без кавычек, без нумерации.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Дешевая и быстрая модель
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты помощник, который создает короткие, интересные подсказки для мест. "
                        "Отвечай только подсказкой, без дополнительных слов, без кавычек."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,  # Немного креативности
            max_tokens=50,  # Ограничение длины
            timeout=10,  # Timeout 10 секунд
        )

        hint = response.choices[0].message.content.strip()

        # Убираем кавычки, если AI их добавил
        hint = hint.strip('"').strip("'").strip()

        # ВАЛИДАЦИЯ: Проверяем, что подсказка не упоминает другие места
        # Ищем упоминания других названий мест (кроме текущего)
        # Это простая проверка - можно улучшить
        place_name_lower = place_name.lower()
        hint_lower = hint.lower()

        # Если в подсказке есть название места, но не текущего - предупреждение
        # (это не идеальная проверка, но поможет поймать очевидные ошибки)
        if place_name_lower not in hint_lower and len(place_name.split()) > 1:
            # Если название места состоит из нескольких слов, проверяем частично
            place_words = [w.lower() for w in place_name.split() if len(w) > 3]
            if not any(word in hint_lower for word in place_words):
                logger.warning(f"⚠️ Подсказка для '{place_name}' может упоминать другое место: '{hint[:50]}...'")

        # Обрезаем до 200 символов (лимит БД)
        if len(hint) > 200:
            hint = hint[:197] + "..."

        logger.info(f"✅ Сгенерирована подсказка для '{place_name}': {hint[:50]}...")
        return hint

    except Exception as e:
        logger.error(f"❌ Ошибка генерации подсказки для '{place_name}': {e}")
        return None


def generate_hint_for_place(place) -> bool:
    """
    Генерирует подсказку для объекта TaskPlace и сохраняет в БД

    Args:
        place: Объект TaskPlace

    Returns:
        True если подсказка успешно сгенерирована и сохранена
    """
    if not place:
        return False

    # Если уже есть подсказка, пропускаем
    if place.task_hint:
        logger.debug(f"Место '{place.name}' уже имеет подсказку, пропускаем")
        return False

    hint = generate_task_hint(
        place_name=place.name,
        category=place.category,
        place_type=place.place_type or "",
        description=place.description,
    )

    if hint:
        place.task_hint = hint
        return True

    return False
