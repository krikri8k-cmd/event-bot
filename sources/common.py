import datetime as dt
import hashlib
import re
import unicodedata


def norm_text(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).strip()
    return re.sub(r"\s+", " ", s)


def make_external_id(
    source_prefix: str, *, url: str, title: str, starts_at_utc: dt.datetime | None
) -> str:
    """
    Делает стабильный external_id для ON CONFLICT:
      hash( source_prefix + '|' + url + '|' + title + '|' + starts_at_iso )
    """
    base = f"{source_prefix}|{url}|{norm_text(title)}|{(starts_at_utc and starts_at_utc.replace(microsecond=0, tzinfo=dt.UTC).isoformat())}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()
