#!/usr/bin/env python3
"""
Умная система генерации событий на основе реальных мест
Обучаем GPT на реальных данных!
"""

import asyncio
from typing import Any

from ai_utils import _make_client

# from real_places_data import REAL_PLACES  # Удалено при очистке проекта
from utils.geo_utils import haversine_km


class SmartEventGenerator:
    def __init__(self):
        # self.real_places = REAL_PLACES.get("moscow", [])  # Удалено при очистке проекта
        self.real_places = []  # Пустой список, так как real_places_data удален

    def find_nearby_places(self, lat: float, lng: float, radius_km: int = 5) -> list[dict]:
        """
        Находит реальные места поблизости
        """
        nearby_places = []

        for place in self.real_places:
            distance = haversine_km(lat, lng, place["lat"], place["lng"])
            if distance <= radius_km:
                place_with_distance = place.copy()
                place_with_distance["distance_km"] = round(distance, 1)
                nearby_places.append(place_with_distance)

        # Сортируем по расстоянию
        nearby_places.sort(key=lambda x: x["distance_km"])
        return nearby_places

    def create_context_for_gpt(self, nearby_places: list[dict]) -> str:
        """
        Создает контекст для GPT на основе реальных мест
        """
        if not nearby_places:
            return "В этой области нет известных мест для событий."

        context = "Вот реальные места поблизости, где могут проходить события:\n\n"

        for place in nearby_places:
            context += f"📍 {place['name']} (в {place['distance_km']} км)\n"
            context += f"   Тип: {place['type']}\n"
            context += f"   Описание: {place['description']}\n"
            context += f"   Типичные события: {', '.join(place['typical_events'])}\n\n"

        context += """
Инструкции для генерации событий:
1. Генерируй события ТОЛЬКО для указанных мест
2. Используй типичные события как основу, но делай их более конкретными
3. Добавляй реальные детали: время, описание, стоимость
4. Делай события разнообразными: от бесплатных до платных
5. Учитывай сезонность и время года
6. События должны быть реалистичными и интересными
"""

        return context

    async def generate_smart_events(
        self, lat: float, lng: float, radius_km: int = 5, count: int = 5
    ) -> list[dict[str, Any]]:
        """
        Генерирует умные события на основе реальных мест
        """
        print("🧠 Ищем реальные места поблизости...")
        nearby_places = self.find_nearby_places(lat, lng, radius_km)

        if not nearby_places:
            print("❌ Нет известных мест поблизости")
            return []

        print(f"✅ Найдено {len(nearby_places)} реальных мест:")
        for place in nearby_places:
            print(f"   📍 {place['name']} ({place['distance_km']} км)")

        # Создаем контекст для GPT
        context = self.create_context_for_gpt(nearby_places)

        # Генерируем события с контекстом
        print("🤖 Генерируем события на основе реальных мест...")

        prompt = f"""
{context}

Сгенерируй {count} интересных событий для указанных мест. 
Каждое событие должно включать:
- Название события
- Место проведения (одно из указанных мест)
- Время проведения
- Краткое описание
- Тип события (бесплатное/платное)

Формат ответа:
1. Название события - Место проведения
   Время: XX:XX
   Описание: ...
   Тип: бесплатное/платное

2. Название события - Место проведения
   Время: XX:XX
   Описание: ...
   Тип: бесплатное/платное
"""

        try:
            # Используем OpenAI API напрямую
            client = _make_client()
            if client is None:
                print("❌ Не удалось подключиться к OpenAI API")
                return []

            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Ты помощник, который генерирует события для реальных мест. Отвечай в указанном формате.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
            )

            events_text = completion.choices[0].message.content or ""

            # Парсим ответ GPT
            events = self.parse_events_from_text(events_text, nearby_places)

            print(f"✅ Сгенерировано {len(events)} умных событий")
            return events

        except Exception as e:
            print(f"❌ Ошибка генерации: {e}")
            return []

    def parse_events_from_text(self, text: str, nearby_places: list[dict]) -> list[dict[str, Any]]:
        """
        Парсит события из текста GPT
        """
        events = []
        lines = text.split("\n")

        current_event = {}

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Новое событие (начинается с цифры)
            if line[0].isdigit() and ". " in line:
                if current_event:
                    events.append(current_event)

                # Парсим название и место
                parts = line.split(" - ")
                if len(parts) >= 2:
                    title = parts[0].split(". ", 1)[1] if ". " in parts[0] else parts[0]
                    location = parts[1]

                    # Находим координаты места
                    place_coords = self.find_place_coordinates(location, nearby_places)

                    current_event = {
                        "title": title,
                        "location_name": location,
                        "lat": place_coords.get("lat"),
                        "lng": place_coords.get("lng"),
                        "source": "smart_ai",
                    }

            # Время
            elif line.startswith("Время:"):
                current_event["time"] = line.replace("Время:", "").strip()

            # Описание
            elif line.startswith("Описание:"):
                current_event["description"] = line.replace("Описание:", "").strip()

            # Тип
            elif line.startswith("Тип:"):
                current_event["type"] = line.replace("Тип:", "").strip()

        # Добавляем последнее событие
        if current_event:
            events.append(current_event)

        return events

    def find_place_coordinates(self, location_name: str, nearby_places: list[dict]) -> dict:
        """
        Находит координаты места по названию
        """
        for place in nearby_places:
            if place["name"].lower() in location_name.lower():
                return {"lat": place["lat"], "lng": place["lng"]}

        # Если не найдено, возвращаем координаты первого места
        if nearby_places:
            return {"lat": nearby_places[0]["lat"], "lng": nearby_places[0]["lng"]}

        return {"lat": None, "lng": None}


# Тестовая функция
async def test_smart_generator():
    print("🧠 Тестируем умную генерацию событий...")

    generator = SmartEventGenerator()
    events = await generator.generate_smart_events(55.7558, 37.6176, 5, 3)

    print("\n🎯 Результат:")
    for i, event in enumerate(events, 1):
        print(f"{i}. {event['title']}")
        print(f"   📍 {event['location_name']}")
        print(f"   ⏰ {event.get('time', 'Время не указано')}")
        print(f"   📝 {event.get('description', 'Описание не указано')}")
        print(f"   💰 {event.get('type', 'Тип не указан')}")
        print()


if __name__ == "__main__":
    asyncio.run(test_smart_generator())
