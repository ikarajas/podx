from __future__ import annotations

import re
import html


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


__all__ = ["clean_html"]

