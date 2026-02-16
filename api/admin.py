from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import text

from api.app import get_engine

router = APIRouter()


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
def translation_backfill():
    """Запуск догоняющего перевода title_en для событий с NULL. Возвращает статистику."""
    from utils.backfill_translation import run_backfill

    result = run_backfill()
    return {
        "processed": result["processed"],
        "translated": result["translated"],
        "skipped": result["skipped"],
    }
