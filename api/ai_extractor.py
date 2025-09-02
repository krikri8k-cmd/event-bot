#!/usr/bin/env python3
"""
Модуль извлечения событий через LLM
"""

from __future__ import annotations

import json
import logging
import os
import re

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (compatible; EventBot/1.0; +https://github.com/krikri8k-cmd/event-bot)"


def fetch_html(url: str, timeout: int = 30) -> str:
    """Download HTML with basic headers. Raises for 4xx/5xx."""
    resp = requests.get(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.text


def extract_main_text(html: str) -> str:
    """Extract 'main' text (strip scripts/styles)."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.find("div", id="content") or soup
    text = main.get_text("\n", strip=True)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:120_000]


def _extract_json_from_text(s: str) -> list[dict]:
    try:
        start = s.find("[")
        end = s.rfind("]")
        if start != -1 and end != -1 and end > start:
            return json.loads(s[start : end + 1])
    except Exception:
        log.exception("Failed to parse JSON from model output")
    return []


def call_openai_for_events(
    text: str, *, source_url: str | None = None, model: str | None = None
) -> list[dict]:
    """
    Call OpenAI to extract events. If no OPENAI_API_KEY is set, returns [] so CI doesn't fail.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log.warning("OPENAI_API_KEY is not set; returning empty result.")
        return []

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        mdl = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        system = "You are a precise data-extraction assistant. Return only valid JSON."
        user = (
            "Extract an array of event objects from the text. "
            "Each object must include: title, start_datetime (ISO8601), "
            "venue_name, address (if any), city, country, url.\n"
            "Return ONLY a JSON array, no prose.\n\n"
            f"SOURCE_URL: {source_url or '-'}\n\n"
            f"TEXT:\n{text}"
        )

        resp = client.chat.completions.create(
            model=mdl,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
        )
        content = resp.choices[0].message.content or ""
        return _extract_json_from_text(content)
    except Exception as e:
        log.exception("OpenAI extraction failed: %s", e)
        return []
