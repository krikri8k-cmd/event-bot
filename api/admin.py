from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import text

from api.app import get_engine

router = APIRouter()


@router.get("/diagnose-db")
def diagnose_db():
    """
    Диагностика подключения к БД (для поиска UndefinedColumnError).
    Выполняет запросы из того же подключения, что и приложение.
    Сравни host/port/database и список колонок events_community с Railway UI.
    """
    eng = get_engine()
    result = {}
    try:
        with eng.connect() as conn:
            # 1) К какой БД подключены
            row = conn.execute(text("SELECT current_database()")).scalar()
            result["current_database"] = row[0] if row else None
            row = conn.execute(text("SELECT current_schema()")).scalar()
            result["current_schema"] = row[0] if row else None
            row = conn.execute(text("SELECT version()")).scalar()
            result["version"] = (row[0][:200] + "...") if row and len(row[0]) > 200 else (row[0] if row else None)
            # 2) Connection info (masked)
            try:
                url = eng.url
                result["connection"] = {
                    "host": url.host,
                    "port": url.port,
                    "database": url.database,
                }
            except Exception as e:
                result["connection"] = {"error": str(e)}
            # 3) В какой схеме лежит events_community
            rows = conn.execute(
                text(
                    "SELECT table_schema, table_name FROM information_schema.tables "
                    "WHERE table_name = 'events_community'"
                )
            ).fetchall()
            result["events_community_tables"] = [{"table_schema": r[0], "table_name": r[1]} for r in rows]
            # 4) Список колонок events_community (именно из этого подключения)
            rows = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'events_community' ORDER BY ordinal_position"
                )
            ).fetchall()
            result["events_community_columns"] = [r[0] for r in rows]
            result["has_title_en"] = "title_en" in result["events_community_columns"]
            result["has_description_en"] = "description_en" in result["events_community_columns"]
    except Exception as e:
        result["error"] = str(e)
    return result


class SourceIn(BaseModel):
    type: str  # 'ics' | 'html_nexudus'
    url: HttpUrl
    region: str | None = None
    enabled: bool = True
    freq_minutes: int = 120
    notes: str | None = None


@router.get("/sources")
def list_sources():
    eng = get_engine()
    with eng.begin() as conn:
        rows = conn.execute(text("SELECT * FROM event_sources ORDER BY id")).mappings().all()
        return {"items": [dict(r) for r in rows], "count": len(rows)}


@router.post("/sources")
def upsert_source(s: SourceIn):
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(
            text("""
          INSERT INTO event_sources (type, url, region, enabled, freq_minutes, notes)
          VALUES (:type, :url, :region, :enabled, :freq, :notes)
          ON CONFLICT (url) DO UPDATE SET
            type=EXCLUDED.type,
            region=EXCLUDED.region,
            enabled=EXCLUDED.enabled,
            freq_minutes=EXCLUDED.freq_minutes,
            notes=EXCLUDED.notes
        """),
            dict(
                type=s.type,
                url=str(s.url),
                region=s.region,
                enabled=s.enabled,
                freq=s.freq_minutes,
                notes=s.notes,
            ),
        )
    return {"ok": True}


@router.post("/sources/{source_id}/toggle")
def toggle_source(source_id: int, enabled: bool):
    eng = get_engine()
    with eng.begin() as conn:
        n = conn.execute(
            text("UPDATE event_sources SET enabled=:en WHERE id=:id"),
            dict(en=enabled, id=source_id),
        ).rowcount
        if n == 0:
            raise HTTPException(404, "not found")
    return {"ok": True}


@router.post("/ingest/run")
def run_ingest_now():
    from scheduler import ingest_once

    ingest_once()
    return {"ok": True}


@router.post("/translation/backfill")
def translation_backfill(full: bool = True):
    """
    Догоняющий перевод событий без EN.
    full=True (по умолчанию): переводим title, description, location_name (качественный EN).
    full=False: только заголовки батчем (быстрее).
    """
    from utils.backfill_translation import run_backfill

    result = run_backfill(full=full)
    return {
        "processed": result["processed"],
        "translated": result["translated"],
        "skipped": result["skipped"],
    }
