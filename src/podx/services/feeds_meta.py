from __future__ import annotations

import json
import hashlib
import base64
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from podx.services.config import Config


_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}


def _slugify(text: str, max_len: int = 48) -> str:
    s = (
        text
        .strip()
        .lower()
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        s = "podcast"
    return s[:max_len]


def _canonicalize_url(url: str) -> str:
    from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

    p = urlparse(url)
    scheme = p.scheme.lower()
    netloc = p.netloc.lower()
    path = p.path or "/"
    params = p.params
    # Drop fragment
    fragment = ""
    # Sort query params, drop known tracking
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k not in _TRACKING_PARAMS]
    q.sort()
    query = urlencode(q)
    return urlunparse((scheme, netloc, path, params, query, fragment))


def _short_id(url: str, length: int = 8) -> str:
    canon = _canonicalize_url(url)
    digest = hashlib.sha256(canon.encode("utf-8")).digest()
    # Base32 without padding gives alphanum, uppercase; make lowercase for aesthetics
    b32 = base64.b32encode(digest).decode("ascii").rstrip("=").lower()
    return b32[:length]


@dataclass
class FeedMeta:
    key: str
    feed_url: str
    title: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    icon_url: Optional[str] = None
    etag: Optional[str] = None
    last_modified: Optional[str] = None  # HTTP-date string
    last_fetch: Optional[str] = None  # ISO timestamp


class FeedsMetaService:
    """Manage cached metadata for feeds and stable subscription keys.

    Data is stored in ``feeds_meta.json`` under the configured ``root_dir``.
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.path = cfg.root_dir / "feeds_meta.json"
        self._by_key: dict[str, FeedMeta] = {}
        self._by_url: dict[str, str] = {}  # feed_url -> key
        self._load()

    # Persistence
    def _load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text())
            self._by_key = {item["key"]: FeedMeta(**item) for item in data}
            self._by_url = {m.feed_url: m.key for m in self._by_key.values()}
        else:
            self._by_key = {}
            self._by_url = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(m) for m in self._by_key.values()]
        self.path.write_text(json.dumps(data, indent=2))

    # Keys
    def get_or_create_key(self, name: str, feed_url: str) -> str:
        existing = self._by_url.get(feed_url)
        if existing:
            return existing
        base = f"{_slugify(name)}--{_short_id(feed_url)}"
        key = base
        # Ensure uniqueness in case of rare collisions
        i = 2
        while key in self._by_key and self._by_key[key].feed_url != feed_url:
            key = f"{base}-{i}"
            i += 1
        # Create minimal entry and persist
        self._by_key[key] = FeedMeta(key=key, feed_url=feed_url)
        self._by_url[feed_url] = key
        self._save()
        return key

    # Accessors
    def get_by_key(self, key: str) -> Optional[FeedMeta]:
        return self._by_key.get(key)

    def get_by_url(self, feed_url: str) -> Optional[FeedMeta]:
        key = self._by_url.get(feed_url)
        return self._by_key.get(key) if key else None

    def set_meta(self, key: str, **fields) -> None:
        meta = self._by_key.get(key)
        if not meta:
            return
        for k, v in fields.items():
            if hasattr(meta, k):
                setattr(meta, k, v)
        self._save()

    # Directory path helper
    def podcast_dir(self, name: str, feed_url: str) -> Path:
        key = self.get_or_create_key(name, feed_url)
        return self.cfg.root_dir / key

    # Staleness
    def is_stale(self, key: str, ttl_hours: int = 24) -> bool:
        meta = self._by_key.get(key)
        if not meta or not meta.last_fetch:
            return True
        try:
            last = datetime.fromisoformat(meta.last_fetch)
            return datetime.now() - last > timedelta(hours=ttl_hours)
        except Exception:
            return True


__all__ = ["FeedsMetaService", "FeedMeta"]

