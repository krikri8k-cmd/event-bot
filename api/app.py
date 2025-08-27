from __future__ import annotations

import os

from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def get_engine() -> Engine:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return create_engine(url, future=True, pool_pre_ping=True)


def create_app() -> FastAPI:
    app = FastAPI(title="EventBot API (CI)")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/db/ping")
    def db_ping():
        with get_engine().connect() as conn:
            val = conn.execute(text("SELECT 1")).scalar_one()
        return {"db": "ok", "value": int(val)}

    @app.get("/events/nearby")
    def events_nearby(lat: float, lng: float, radius_km: float = 5):
        """Поиск событий в радиусе от координат"""
        with get_engine().connect() as conn:
            # Простой поиск по прямоугольнику (для smoke-тестов)
            # В реальном проекте используй PostGIS ST_DWithin
            lat_min, lat_max = lat - radius_km / 111, lat + radius_km / 111
            lng_min, lng_max = lng - radius_km / 111, lng + radius_km / 111

            result = conn.execute(
                text("""
                    SELECT id, title, lat, lng, starts_at, created_at
                    FROM events 
                    WHERE lat BETWEEN :lat_min AND :lat_max 
                      AND lng BETWEEN :lng_min AND :lng_max
                    ORDER BY starts_at
                """),
                {
                    "lat_min": lat_min,
                    "lat_max": lat_max,
                    "lng_min": lng_min,
                    "lng_max": lng_max,
                },
            )
            events = []
            for row in result:
                events.append(
                    {
                        "id": row.id,
                        "title": row.title,
                        "lat": float(row.lat),
                        "lng": float(row.lng),
                        "starts_at": row.starts_at.isoformat() if row.starts_at else None,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    }
                )
        return events

    return app


# для импортов типа "from api.app import app"
app = create_app()
