from __future__ import annotations

import json
import hashlib
import base64
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

from .feeds_meta import FeedsMetaService


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _make_episode_id(guid: Optional[str], enclosure: Optional[str], published: Optional[str], title: Optional[str]) -> str:
    if guid:
        return f"guid:{guid}"
    if enclosure:
        return f"encl:{enclosure}"
    key = f"{published or ''}|{_norm_text(title or '')}"
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return "h:" + base64.b32encode(digest).decode("ascii").rstrip("=").lower()[:16]


@dataclass
class EpisodeIndexEntry:
    episode_id: str
    title: str
    published_date: str | None
    guid: str | None = None
    enclosure_url: str | None = None
    status: str = "transcribed"  # one of: transcribed, failed
    episode_dir: str | None = None
    vtt_path: str | None = None
    txt_path: str | None = None
    # Transcript timestamps (persisted so UI shows accurate generation time)
    created_at: str | None = None
    updated_at: str | None = None
    error: str | None = None
    # Summary metadata (persisted for future summary UI)
    summary_path: str | None = None
    summary_updated_at: str | None = None


class EpisodesIndexService:
    """Persist per-subscription episode statuses in JSON.

    Stored at ``root_dir/{key}/episodes_index.json``.
    """

    def __init__(self, feeds_meta: FeedsMetaService) -> None:
        self.feeds_meta = feeds_meta

    def _index_path(self, key: str) -> Path:
        return self.feeds_meta.cfg.root_dir / key / "episodes_index.json"

    def _load_map(self, key: str) -> Dict[str, EpisodeIndexEntry]:
        p = self._index_path(key)
        if not p.exists():
            return {}
        data = json.loads(p.read_text())
        return {item["episode_id"]: EpisodeIndexEntry(**item) for item in data}

    def _save_map(self, key: str, mp: Dict[str, EpisodeIndexEntry]) -> None:
        p = self._index_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(v) for v in mp.values()]
        p.write_text(json.dumps(data, indent=2))

    # Query
    def find(self, key: str, guid: Optional[str], enclosure: Optional[str], published: Optional[str], title: Optional[str]) -> Optional[EpisodeIndexEntry]:
        mp = self._load_map(key)
        # Prefer direct keys
        if guid and f"guid:{guid}" in mp:
            return mp[f"guid:{guid}"]
        if enclosure and f"encl:{enclosure}" in mp:
            return mp[f"encl:{enclosure}"]
        # Fallback fuzzy key
        h = _make_episode_id(None, None, published, title)
        return mp.get(h)

    def mark_transcribed(
        self,
        key: str,
        *,
        title: str,
        published_date: Optional[str],
        guid: Optional[str],
        enclosure_url: Optional[str],
        episode_dir: Path,
        vtt_path: Path,
        txt_path: Path,
    ) -> EpisodeIndexEntry:
        mp = self._load_map(key)
        episode_id = _make_episode_id(guid, enclosure_url, published_date, title)
        now = datetime.now().isoformat()
        entry = mp.get(episode_id) or EpisodeIndexEntry(
            episode_id=episode_id, title=title, published_date=published_date, guid=guid, enclosure_url=enclosure_url
        )
        entry.status = "transcribed"
        entry.episode_dir = str(episode_dir)
        entry.vtt_path = str(vtt_path)
        entry.txt_path = str(txt_path)
        entry.error = None
        entry.updated_at = now
        if not entry.created_at:
            entry.created_at = now
        mp[episode_id] = entry
        self._save_map(key, mp)
        return entry

    def mark_failed(
        self,
        key: str,
        *,
        title: str,
        published_date: Optional[str],
        guid: Optional[str],
        enclosure_url: Optional[str],
        error: str,
    ) -> EpisodeIndexEntry:
        mp = self._load_map(key)
        episode_id = _make_episode_id(guid, enclosure_url, published_date, title)
        now = datetime.now().isoformat()
        entry = mp.get(episode_id) or EpisodeIndexEntry(
            episode_id=episode_id, title=title, published_date=published_date, guid=guid, enclosure_url=enclosure_url
        )
        entry.status = "failed"
        entry.error = error
        entry.updated_at = now
        if not entry.created_at:
            entry.created_at = now
        mp[episode_id] = entry
        self._save_map(key, mp)
        return entry

    def mark_summary(
        self,
        key: str,
        *,
        title: str,
        published_date: Optional[str],
        guid: Optional[str],
        enclosure_url: Optional[str],
        summary_path: Path,
        episode_dir: Optional[Path] = None,
    ) -> EpisodeIndexEntry:
        """Record or update summary metadata for an episode.

        Notes
        - This mirrors ``mark_transcribed`` but does not change transcript
          timestamps. ``summary_updated_at`` is tracked separately so the UI
          can display accurate generation times for both transcript and summary.
        - Summary generation is not yet wired up in the UI; this method prepares
          persistent storage for that future feature.
        """
        mp = self._load_map(key)
        episode_id = _make_episode_id(guid, enclosure_url, published_date, title)
        now = datetime.now().isoformat()
        entry = mp.get(episode_id) or EpisodeIndexEntry(
            episode_id=episode_id, title=title, published_date=published_date, guid=guid, enclosure_url=enclosure_url
        )
        # Keep transcript timestamps intact; only update summary fields here.
        if episode_dir is not None:
            entry.episode_dir = str(episode_dir)
        entry.summary_path = str(summary_path)
        entry.summary_updated_at = now
        mp[episode_id] = entry
        self._save_map(key, mp)
        return entry


__all__ = ["EpisodesIndexService", "EpisodeIndexEntry"]
