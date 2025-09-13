#!/usr/bin/env python3
"""
Простой веб-сервер для health-эндпоинтов
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web.health import router as health_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("🚀 Запуск health-сервера...")
    yield
    logger.info("🛑 Остановка health-сервера...")


# Создаем FastAPI приложение
app = FastAPI(
    title="Event Bot Health API",
    description="Health-эндпоинты для мониторинга Event Bot",
    version="1.0.0",
    lifespan=lifespan,
)

# Добавляем CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене ограничить
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
app.include_router(health_router, prefix="/api/v1")


@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "service": "Event Bot Health API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/api/v1/health/kudago",
            "metrics": "/api/v1/health/kudago/metrics",
            "status": "/api/v1/health/kudago/status",
        },
    }


@app.get("/health")
async def health():
    """Общий health-чек"""
    return {"status": "ok", "service": "event-bot-health"}


if __name__ == "__main__":
    import uvicorn

    # Настройки из ENV
    host = os.getenv("HEALTH_HOST", "0.0.0.0")
    port = int(os.getenv("HEALTH_PORT", "8080"))

    logger.info(f"🌐 Запуск health-сервера на {host}:{port}")

    uvicorn.run("web.server:app", host=host, port=port, reload=False, log_level="info")
