from __future__ import annotations

from typing import List, Optional, Tuple
from urllib.request import urlopen, Request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from ..models import FeedEpisode


def _parse_duration(text: str) -> int | None:
    try:
        parts = text.split(":")
        parts = [int(p) for p in parts]
        if len(parts) == 3:
            h, m, s = parts
        elif len(parts) == 2:
            h = 0
            m, s = parts
        elif len(parts) == 1:
            h = 0
            m = 0
            s = parts[0]
        else:
            return None
        return h * 3600 + m * 60 + s
    except Exception:
        return None


class RssService:
    """Download and parse podcast RSS feeds."""

    ITUNES_NS = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"

    def fetch_episodes(self, feed_url: str) -> List[FeedEpisode]:
        """Return a list of episodes for the given feed URL."""
        with urlopen(feed_url) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        episodes: List[FeedEpisode] = []
        for item in root.findall(".//item"):
            title = item.findtext("title", default="")
            description = item.findtext("description", default="")
            pub_text = item.findtext("pubDate")
            published = parsedate_to_datetime(pub_text) if pub_text else None
            dur_text = item.findtext(self.ITUNES_NS + "duration")
            duration = _parse_duration(dur_text) if dur_text else None
            art_el = item.find(self.ITUNES_NS + "image")
            artwork = art_el.get("href") if art_el is not None else None
            episodes.append(
                FeedEpisode(
                    title=title,
                    description=description,
                    published=published,
                    duration=duration,
                    artwork_url=artwork,
                    transcribed=False,
                )
            )
        return episodes

    def fetch_channel_meta(
        self,
        feed_url: str,
        *,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
        """Return (title, description, icon_url, new_etag, new_last_modified).

        Sends conditional headers when provided and returns ``(None, None, None, etag, last_modified)``
        when a 304 is received (best-effort; urllib does not expose status on older Python versions,
        so failures fall back to parsing).
        """
        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        req = Request(feed_url, headers=headers)
        with urlopen(req) as resp:
            new_etag = resp.headers.get("ETag")
            new_last_mod = resp.headers.get("Last-Modified")
            data = resp.read()
        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            return None, None, None, new_etag, new_last_mod
        title = root.findtext("channel/title")
        description = root.findtext("channel/description")
        # Prefer channel-level itunes:image, fallback to item-level or None
        image_el = root.find("channel/" + self.ITUNES_NS + "image")
        icon_url = image_el.get("href") if image_el is not None else None
        return title, description, icon_url, new_etag, new_last_mod


__all__ = ["RssService", "_parse_duration"]
