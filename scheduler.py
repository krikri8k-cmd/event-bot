import os

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text

from ingest.upsert import upsert_event
from sources.ics import fetch_ics, parse_ics
from sources.nexudus import discover_event_ics_links

INGEST_DEFAULT_FREQ_MIN = int(os.getenv("INGEST_DEFAULT_FREQ_MIN", "120"))
INGEST_MAX_FAILS = int(os.getenv("INGEST_MAX_FAILS", "5"))


def get_engine():
    from database import get_engine  # используем engine из database

    return get_engine()


def _due_sources(engine):
    sql = text("""
      SELECT * FROM event_sources
      WHERE enabled = TRUE
        AND (last_fetch_at IS NULL OR NOW() - last_fetch_at >= (freq_minutes || ' minutes')::interval)
      ORDER BY COALESCE(last_fetch_at, to_timestamp(0))
      LIMIT 50
    """)
    with engine.begin() as conn:
        return [dict(r) for r in conn.execute(sql).mappings()]


def _update_source_meta(engine, src_id, *, etag=None, last_modified=None, status=None, ok=True):
    with engine.begin() as conn:
        if ok:
            conn.execute(
                text("""
              UPDATE event_sources
                 SET last_fetch_at = NOW(),
                     last_status = :st,
                     etag = COALESCE(:etag, etag),
                     last_modified = COALESCE(:lm, last_modified),
                     fail_count = 0
               WHERE id = :id
            """),
                dict(id=src_id, st=status, etag=etag, lm=last_modified),
            )
        else:
            conn.execute(
                text("""
              UPDATE event_sources
                 SET last_fetch_at = NOW(),
                     last_status = :st,
                     fail_count = fail_count + 1,
                     enabled = CASE WHEN fail_count + 1 >= :maxf THEN FALSE ELSE enabled END
               WHERE id = :id
            """),
                dict(id=src_id, st=status, maxf=INGEST_MAX_FAILS),
            )


def ingest_once():
    eng = get_engine()
    for src in _due_sources(eng):
        try:
            if src["type"] == "ics":
                resp = fetch_ics(
                    src["url"], etag=src.get("etag"), last_modified=src.get("last_modified")
                )
                if resp.status_code == 304:
                    _update_source_meta(eng, src["id"], status=304, ok=True)
                    continue
                resp.raise_for_status()
                new_etag = resp.headers.get("ETag")
                new_lm = resp.headers.get("Last-Modified")
                count = 0
                for row in parse_ics(
                    resp.content,
                    source_prefix=f"ics.{src.get('region') or 'id'}",
                    calendar_url=src["url"],
                ):
                    upsert_event(eng, row)
                    count += 1
                _update_source_meta(
                    eng,
                    src["id"],
                    etag=new_etag,
                    last_modified=new_lm,
                    status=resp.status_code,
                    ok=True,
                )
                print(f"[ICS] {src['url']} → upserted {count}")
            elif src["type"] == "html_nexudus":
                ics_links = discover_event_ics_links(src["url"])
                count = 0
                for ics_url in ics_links:
                    resp = fetch_ics(ics_url)
                    if resp.status_code != 200:
                        continue
                    for row in parse_ics(
                        resp.content,
                        source_prefix=f"nexudus.{src.get('region') or 'id'}",
                        calendar_url=ics_url,
                    ):
                        upsert_event(eng, row)
                        count += 1
                _update_source_meta(eng, src["id"], status=200, ok=True)
                print(f"[NEXUDUS] {src['url']} → upserted {count}")
            else:
                _update_source_meta(eng, src["id"], status=400, ok=False)
        except requests.HTTPError as e:
            _update_source_meta(
                eng, src["id"], status=e.response.status_code if e.response else 500, ok=False
            )
        except Exception:
            _update_source_meta(eng, src["id"], status=500, ok=False)


def start_scheduler():
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(
        ingest_once, "interval", minutes=5, id="ingest-cycle", max_instances=1, coalesce=True
    )
    sched.start()
    return sched
