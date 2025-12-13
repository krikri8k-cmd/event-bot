#!/usr/bin/env python3
"""Проверка мест Чангу по координатам"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import load_settings
from database import TaskPlace, get_session, init_engine

# Координаты Чангу (примерные границы)
CANGGU_LAT_MIN = -8.70
CANGGU_LAT_MAX = -8.60
CANGGU_LNG_MIN = 115.10
CANGGU_LNG_MAX = 115.20

settings = load_settings()
init_engine(settings.database_url)
session = get_session()

# Все места Бали
all_bali = (
    session.query(TaskPlace)
    .filter(
        TaskPlace.category == "food",
        TaskPlace.region == "bali",
        TaskPlace.task_type == "island",
    )
    .all()
)

print(f"Total Bali places: {len(all_bali)}\n")

# Места в Чангу (по координатам)
canggu_places = [
    p for p in all_bali if CANGGU_LAT_MIN <= p.lat <= CANGGU_LAT_MAX and CANGGU_LNG_MIN <= p.lng <= CANGGU_LNG_MAX
]

print(f"Canggu places (by coordinates): {len(canggu_places)}\n")
for i, p in enumerate(canggu_places, 1):
    print(f"{i}. {p.name}")
    print(f"   Coords: {p.lat:.4f}, {p.lng:.4f}")
    print(f"   Type: {p.place_type}")
    print()

# Места в Убуде (по координатам)
UBUD_LAT_MIN = -8.55
UBUD_LAT_MAX = -8.45
UBUD_LNG_MIN = 115.24
UBUD_LNG_MAX = 115.28

ubud_places = [p for p in all_bali if UBUD_LAT_MIN <= p.lat <= UBUD_LAT_MAX and UBUD_LNG_MIN <= p.lng <= UBUD_LNG_MAX]

print(f"\nUbud places (by coordinates): {len(ubud_places)}\n")
for i, p in enumerate(ubud_places[:10], 1):
    print(f"{i}. {p.name}")
    print(f"   Coords: {p.lat:.4f}, {p.lng:.4f}")
    print(f"   Type: {p.place_type}")
    print()
