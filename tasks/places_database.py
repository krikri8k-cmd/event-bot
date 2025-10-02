"""
База мест для MVP - хардкод вместо Google Places API
Простой и надежный подход для начального тестирования
"""

# База мест по категориям для MVP
PLACES_DATABASE = {
    "body": [
        {
            "name": "Пляж Кута",
            "lat": -8.7183,
            "lng": 115.1686,
            "description": "Популярный пляж для прогулок и спорта",
            "google_maps_url": "https://maps.google.com/?q=-8.7183,115.1686",
        },
        {
            "name": "Парк Убуда",
            "lat": -8.5069,
            "lng": 115.2625,
            "description": "Зеленый парк в центре Убуда",
            "google_maps_url": "https://maps.google.com/?q=-8.5069,115.2625",
        },
        {
            "name": "Спортзал в Семиньяке",
            "lat": -8.6900,
            "lng": 115.1700,
            "description": "Современный фитнес-центр",
            "google_maps_url": "https://maps.google.com/?q=-8.6900,115.1700",
        },
    ],
    "spirit": [
        {
            "name": "Храм Танах Лот",
            "lat": -8.6211,
            "lng": 115.0864,
            "description": "Священный храм на скале",
            "google_maps_url": "https://maps.google.com/?q=-8.6211,115.0864",
        },
        {
            "name": "Смотровая площадка Кампухан Ридж",
            "lat": -8.5089,
            "lng": 115.2567,
            "description": "Панорамный вид на рисовые террасы",
            "google_maps_url": "https://maps.google.com/?q=-8.5089,115.2567",
        },
        {
            "name": "Пляж Паданг Паданг",
            "lat": -8.8300,
            "lng": 115.0800,
            "description": "Тихий пляж для медитации",
            "google_maps_url": "https://maps.google.com/?q=-8.8300,115.0800",
        },
    ],
    "career": [
        {
            "name": "Кафе в Убуда",
            "lat": -8.5069,
            "lng": 115.2625,
            "description": "Тихие кафе для работы",
            "google_maps_url": "https://maps.google.com/?q=-8.5069,115.2625",
        },
        {
            "name": "Коворкинг в Семиньяке",
            "lat": -8.6900,
            "lng": 115.1700,
            "description": "Современное рабочее пространство",
            "google_maps_url": "https://maps.google.com/?q=-8.6900,115.1700",
        },
        {
            "name": "Библиотека в Денпасаре",
            "lat": -8.6500,
            "lng": 115.2167,
            "description": "Публичная библиотека",
            "google_maps_url": "https://maps.google.com/?q=-8.6500,115.2167",
        },
    ],
    "social": [
        {
            "name": "Танцевальная студия в Убуда",
            "lat": -8.5069,
            "lng": 115.2625,
            "description": "Студия традиционных и современных танцев",
            "google_maps_url": "https://maps.google.com/?q=-8.5069,115.2625",
        },
        {
            "name": "Кафе в Семиньяке",
            "lat": -8.6900,
            "lng": 115.1700,
            "description": "Место для знакомств и общения",
            "google_maps_url": "https://maps.google.com/?q=-8.6900,115.1700",
        },
        {
            "name": "Бильярд в Куте",
            "lat": -8.7183,
            "lng": 115.1686,
            "description": "Бильярдный клуб",
            "google_maps_url": "https://maps.google.com/?q=-8.7183,115.1686",
        },
    ],
}


def get_places_for_category(category: str, user_lat: float, user_lng: float, limit: int = 3):
    """
    Получить места для категории, отсортированные по расстоянию
    """

    places = PLACES_DATABASE.get(category, [])

    # Вычисляем расстояние до каждого места
    for place in places:
        distance = calculate_distance(user_lat, user_lng, place["lat"], place["lng"])
        place["distance_km"] = round(distance, 1)

    # Сортируем по расстоянию и берем ближайшие
    places.sort(key=lambda x: x["distance_km"])
    return places[:limit]


def calculate_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Вычисляет расстояние между двумя точками в км"""
    import math

    # Формула гаверсинуса
    R = 6371  # Радиус Земли в км

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)

    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def get_place_by_name(place_name: str):
    """Найти место по названию"""
    for category_places in PLACES_DATABASE.values():
        for place in category_places:
            if place["name"] == place_name:
                return place
    return None
