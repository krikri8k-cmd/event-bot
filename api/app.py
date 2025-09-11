from __future__ import annotations

import logging
import os

from fastapi import APIRouter, FastAPI, HTTPException, Query
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import load_settings

logger = logging.getLogger(__name__)


_engine: Engine | None = None


def get_engine() -> Engine:
    """Создаёт Engine один раз по первому вызову, беря строку из config."""
    global _engine
    if _engine is None:
        from config import load_settings

        settings = load_settings()
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not set")
        _engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
    return _engine


def create_app() -> FastAPI:
    app = FastAPI(title="EventBot API (CI)")

    # Загружаем настройки
    settings = load_settings()

    # Админ роутер для управления источниками
    from api.admin import router as admin_router

    app.include_router(admin_router, prefix="/admin", tags=["admin"])

    # Meetup OAuth роутер (только если включен)
    if settings.enable_meetup_api:
        oauth_router = APIRouter(prefix="/oauth/meetup", tags=["oauth"])

        @oauth_router.get("/login")
        async def meetup_login():
            from api.oauth_meetup import MeetupOAuth

            mgr = MeetupOAuth()
            if not mgr.client_id:
                raise HTTPException(status_code=500, detail="MEETUP_CLIENT_ID is not configured")
            return {"authorize_url": mgr.authorize_url()}

        @oauth_router.get("/callback")
        async def meetup_callback(
            code: str | None = Query(default=None, description="Authorization code"),
            state: str | None = Query(default=None),
            error: str | None = Query(default=None),
        ):
            """
            OAuth колбэк для Meetup: обмен кода на токены или мок-режим для тестов
            """
            if error:
                raise HTTPException(status_code=400, detail=f"Meetup error: {error}")
            if not code:
                raise HTTPException(status_code=400, detail="Missing code")

            # Мок-режим для локалки/тестов
            if os.getenv("MEETUP_MOCK", "0") == "1":
                return {"ok": True, "code": code, "state": state, "mock": True}

            # Боевой путь: обмен кода на токены
            try:
                from api.oauth_meetup import MeetupOAuth

                mgr = MeetupOAuth()
                bundle = await mgr.exchange_code(code)

                # ⚠️ Осознанно логируем ПОЛНЫЕ значения в консоль (чтобы пользователь мог их скопировать).
                logger.info("MEETUP_ACCESS_TOKEN=%s", bundle.access_token)
                logger.info("MEETUP_REFRESH_TOKEN=%s", bundle.refresh_token)

                return {
                    "ok": True,
                    "code": code,
                    "state": state,
                    "preview": MeetupOAuth.mask_preview(bundle),
                    "note": "Скопируй ПОЛНЫЕ токены из логов uvicorn и добавь их в .env.local",
                    "env_keys": ["MEETUP_ACCESS_TOKEN", "MEETUP_REFRESH_TOKEN"],
                }
            except Exception as e:
                logger.error("Ошибка обмена кода на токены: %s", e)
                raise HTTPException(status_code=500, detail=f"Failed to exchange code: {str(e)}")

        # Подключаем OAuth роутер
        app.include_router(oauth_router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/db/ping")
    def db_ping():
        with get_engine().connect() as conn:
            val = conn.execute(text("SELECT 1")).scalar_one()
        return {"db": "ok", "value": int(val)}

    @app.get("/events/nearby")
    def events_nearby(lat: float, lng: float, radius_km: float = 5, limit: int = 50, offset: int = Query(0, ge=0)):
        """Поиск событий в радиусе от координат с точным расстоянием"""
        # Валидация входных данных
        if not (-90 <= lat <= 90):
            raise HTTPException(status_code=400, detail="lat must be between -90 and 90")
        if not (-180 <= lng <= 180):
            raise HTTPException(status_code=400, detail="lng must be between -180 and 180")
        if not (1 <= radius_km <= 20):
            raise HTTPException(status_code=400, detail="radius_km must be between 1 and 20")
        if not (1 <= limit <= 100):
            raise HTTPException(status_code=400, detail="limit must be between 1 and 100")

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

            events = [dict(r) for r in rows]
            return {"items": events, "count": len(events)}

    # Meetup sync endpoint (только если включен)
    if settings.enable_meetup_api:

        @app.post("/events/sources/meetup/sync")
        async def sync_meetup(lat: float, lng: float, radius_km: float = 5.0):
            """Синхронизация событий из Meetup API"""
            # Валидация входных данных
            if not (-90 <= lat <= 90):
                raise HTTPException(status_code=400, detail="lat must be between -90 and 90")
            if not (-180 <= lng <= 180):
                raise HTTPException(status_code=400, detail="lng must be between -180 and 180")
            if not (1 <= radius_km <= 20):
                raise HTTPException(status_code=400, detail="radius_km must be between 1 and 20")

            try:
                # Получаем события из Meetup
                import sources.meetup
                from ingest import upsert_events

                events = await sources.meetup.fetch(lat, lng, radius_km)

                # Вставляем в базу данных
                engine = get_engine()
                inserted_count = upsert_events(events, engine)

                return {"inserted": inserted_count}

            except Exception as e:
                return {"error": str(e), "inserted": 0}

    # BaliForum sync endpoint (только если включен)
    if settings.enable_baliforum:

        @app.post("/events/sources/baliforum/sync")
        async def sync_baliforum(lat: float, lng: float, radius_km: float = 5.0):
            """Синхронизация событий из BaliForum"""
            # Валидация входных данных
            if not (-90 <= lat <= 90):
                raise HTTPException(status_code=400, detail="lat must be between -90 and 90")
            if not (-180 <= lng <= 180):
                raise HTTPException(status_code=400, detail="lng must be between -180 and 180")
            if not (1 <= radius_km <= 20):
                raise HTTPException(status_code=400, detail="radius_km must be between 1 and 20")

            try:
                # Получаем события из BaliForum
                import sources.baliforum
                from ingest import upsert_events

                events = sources.baliforum.fetch(lat, lng, radius_km)

                # Вставляем в базу данных
                engine = get_engine()
                inserted_count = upsert_events(events, engine)

                return {"inserted": inserted_count}

            except Exception as e:
                return {"error": str(e), "inserted": 0}

    return app


# для импортов типа "from api.app import app"
app = create_app()

# Запускаем планировщик при старте приложения
try:
    from scheduler import start_scheduler

    start_scheduler()
except Exception:
    # в CI можно не стартовать; либо логируем
    pass
