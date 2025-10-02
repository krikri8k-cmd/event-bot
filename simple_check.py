#!/usr/bin/env python3
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("app.local.env")
engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    # Events without coordinates
    result = conn.execute(text("SELECT COUNT(*) FROM events WHERE source = 'user' AND lat IS NULL"))
    print("Events without lat:", result.fetchone()[0])

    result = conn.execute(text("SELECT COUNT(*) FROM events WHERE source = 'user' AND lng IS NULL"))
    print("Events without lng:", result.fetchone()[0])

    # All user events
    result = conn.execute(text("SELECT COUNT(*) FROM events WHERE source = 'user'"))
    print("Total user events:", result.fetchone()[0])
