from __future__ import annotations

import re
import html
from datetime import date, datetime
from pathlib import Path

from PyQt6.QtGui import QPixmap



_TAG_RE = re.compile(r"<[^>]+>")


def clean_html(text: str | None) -> str:
    """Return display-friendly plain text from HTML-ish strings.

    - Unescapes HTML entities (e.g., &amp; → &)
    - Strips simple tags like <p>, <br>, <em> …
    - Collapses consecutive whitespace to a single space
    """
    if not text:
        return ""
    try:
        s = html.unescape(text)
        s = _TAG_RE.sub(" ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s
    except Exception:
        return str(text)


def format_duration(seconds: int | None) -> str:
    """Return m:ss string for a duration in seconds, or empty string."""
    if seconds is None:
        return ""
    try:
        m = int(seconds) // 60
        s = int(seconds) % 60
        return f"{m:d}:{s:02d}"
    except Exception:
        return ""


def format_episode_meta(dt: datetime | date | None, seconds: int | None) -> str:
    """Compose the compact meta line used in lists and headers.

    Example: "Sep 12, 2024 • 42:03"
    """
    parts: list[str] = []
    try:
        if isinstance(dt, (datetime, date)):
            parts.append(dt.strftime("%b %d, %Y"))
    except Exception:
        pass
    dur = format_duration(seconds)
    if dur:
        parts.append(dur)
    return " \u2022 ".join(parts)


__all__ = [
    "clean_html",
    "format_duration",
    "format_episode_meta",
    "fetch_pixmap",
]


# Simple in-memory cache for fetched pixmaps
_PIXMAP_CACHE: dict[str, QPixmap] = {}


def fetch_pixmap(url: str, *, timeout: float = 5.0) -> QPixmap | None:
    """Load a QPixmap from a local path or HTTP(S) URL with a small cache.

    Returns None on error. Scales are left to callers.
    """
    if not url:
        return None
    cached = _PIXMAP_CACHE.get(url)
    if cached is not None and not cached.isNull():
        return cached
    p = QPixmap()
    try:
        if url.startswith("file://"):
            local = url[len("file://") :]
            p.load(local)
        elif Path(url).exists():
            p.load(url)
        elif url.startswith("http"):
            from urllib.request import urlopen

            with urlopen(url, timeout=timeout) as resp:
                data = resp.read()
            p.loadFromData(data)
    except Exception:
        return None
    if not p.isNull():
        _PIXMAP_CACHE[url] = p
        return p
    return None
