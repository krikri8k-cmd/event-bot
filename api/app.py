from __future__ import annotations

import os

from fastapi import FastAPI, Query
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
    def events_nearby(
        lat: float, lng: float, radius_km: float = 5, limit: int = 50, offset: int = Query(0, ge=0)
    ):
        """Поиск событий в радиусе от координат с точным расстоянием"""
        with get_engine().connect() as conn:
            # Предварительная фильтрация по прямоугольнику для производительности
            delta = radius_km / 111  # примерное расстояние в градусах

            # Точный поиск по гаверсину с distance_km
            rows = (
                conn.execute(
                    text("""
                  SELECT
                    id, title, lat, lng, starts_at, created_at,
                    6371 * 2 * ASIN(
                      SQRT(
                        POWER(SIN(RADIANS((:lat - lat) / 2)), 2) +
                        COS(RADIANS(:lat)) * COS(RADIANS(lat)) *
                        POWER(SIN(RADIANS((:lng - lng) / 2)), 2)
                      )
                    ) AS distance_km
                  FROM events
                  WHERE lat BETWEEN :lat - :d AND :lat + :d
                    AND lng BETWEEN :lng - :d AND :lng + :d
                    AND (
                      6371 * 2 * ASIN(
                        SQRT(
                          POWER(SIN(RADIANS((:lat - lat) / 2)), 2) +
                          COS(RADIANS(:lat)) * COS(RADIANS(lat)) *
                          POWER(SIN(RADIANS((:lng - lng) / 2)), 2)
                        )
                      )
                    ) <= :radius_km
                  ORDER BY distance_km, starts_at NULLS LAST, id
                  LIMIT :limit OFFSET :offset
                """),
                    {
                        "lat": lat,
                        "lng": lng,
                        "d": delta,
                        "radius_km": radius_km,
                        "limit": limit,
                        "offset": offset,
                    },
                )
                .mappings()
                .all()
            )

            return [dict(r) for r in rows]

    return app


# для импортов типа "from api.app import app"
app = create_app()
