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

    return app


# для импортов типа "from api.app import app"
app = create_app()
