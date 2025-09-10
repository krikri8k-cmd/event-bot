import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env.local and .env files (first .env.local, then .env)
_BASE_DIR = Path(__file__).resolve().parent.parent
for fn in (".env.local", ".env"):
    env_file = _BASE_DIR / fn
    if env_file.exists():
        load_dotenv(env_file, override=False, encoding="utf-8-sig")

# Фиче-флаг Meetup (ВЫКЛ по умолчанию)
MEETUP_ENABLED = os.getenv("MEETUP_ENABLED", "0") == "1"

# Мок-режим оставляем как есть
MEETUP_MOCK = os.getenv("MEETUP_MOCK", "0") == "1"

# Опциональная OAuth-конфигурация (не обязательна при выключенном флаге)
MEETUP_CLIENT_ID = os.getenv("MEETUP_CLIENT_ID")
MEETUP_CLIENT_SECRET = os.getenv("MEETUP_CLIENT_SECRET")
MEETUP_REDIRECT_URI = os.getenv("MEETUP_REDIRECT_URI", "http://localhost:8000/oauth/meetup/callback")
