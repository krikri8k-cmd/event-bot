from __future__ import annotations

import os
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

MEETUP_AUTH_URL = "https://secure.meetup.com/oauth2/authorize"
MEETUP_TOKEN_URL = "https://secure.meetup.com/oauth2/access"


def _mask(secret: str | None, keep: int = 6) -> str:
    if not secret:
        return ""
    s = str(secret)
    return s[:keep] + "…" + s[-2:]


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None
    token_type: str | None = None
    obtained_at: float = time.time()

    @property
    def expires_at(self) -> float | None:
        return None if not self.expires_in else self.obtained_at + int(self.expires_in)


class MeetupOAuth:
    """
    Лёгкий OAuth-менеджер для Meetup:
    - строит authorize_url
    - меняет code -> токены
    - умеет рефрешить токен
    - отдаёт headers() для авторизованных запросов
    """

    def __init__(self) -> None:
        self.client_id = os.getenv("MEETUP_CLIENT_ID", "")
        self.client_secret = os.getenv("MEETUP_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv("MEETUP_REDIRECT_URI", "http://localhost:8000/oauth/meetup/callback")

        self._bundle: TokenBundle | None = None
        if os.getenv("MEETUP_ACCESS_TOKEN"):
            self._bundle = TokenBundle(
                access_token=os.getenv("MEETUP_ACCESS_TOKEN", ""),
                refresh_token=os.getenv("MEETUP_REFRESH_TOKEN"),
                expires_in=None,
                token_type="bearer",
            )

    # --------- public API ---------

    def authorize_url(self, state: str | None = None) -> str:
        q = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
        }
        if state:
            q["state"] = state
        return f"{MEETUP_AUTH_URL}?{urlencode(q)}"

    async def exchange_code(self, code: str) -> TokenBundle:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                MEETUP_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.redirect_uri,
                    "code": code,
                },
            )
            r.raise_for_status()
            data = r.json()

        self._bundle = TokenBundle(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            token_type=data.get("token_type"),
            obtained_at=time.time(),
        )
        return self._bundle

    async def refresh(self) -> TokenBundle:
        if not self._bundle or not self._bundle.refresh_token:
            raise RuntimeError("No refresh_token available")

        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                MEETUP_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": self._bundle.refresh_token,
                },
            )
            r.raise_for_status()
            data = r.json()

        self._bundle = TokenBundle(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token") or self._bundle.refresh_token,
            expires_in=data.get("expires_in"),
            token_type=data.get("token_type"),
            obtained_at=time.time(),
        )
        return self._bundle

    def headers(self) -> dict[str, str]:
        if not self._bundle:
            return {}
        return {"Authorization": f"Bearer {self._bundle.access_token}"}

    # --------- helpers ---------

    @staticmethod
    def mask_preview(bundle: TokenBundle) -> dict:
        return {
            "access": _mask(bundle.access_token),
            "refresh": _mask(bundle.refresh_token),
            "expires_in": bundle.expires_in,
        }
