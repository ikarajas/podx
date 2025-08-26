from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Podcast:
    """Simple representation of a podcast in a directory search result."""

    name: str
    feed_url: str
    genres: list[str]


@dataclass
class Subscription:
    """Represents a subscribed podcast."""

    name: str
    feed_url: str
    icon_url: str | None = None


@dataclass
class TranscriptionResult:
    """Represents the result of a transcription run."""

    status: str
    engine: str
    model: str
    language: str
    created_at: str
    vtt_path: Path
    txt_path: Path

    def to_dict(self) -> dict:
        """Convert to a JSON-serialisable dictionary."""
        return {
            "status": self.status,
            "engine": self.engine,
            "model": self.model,
            "language": self.language,
            "created_at": self.created_at,
            "files": [self.vtt_path.name, self.txt_path.name],
        }


@dataclass
class Episode:
    """Represents an ingested podcast episode."""

    podcast: str
    episode_title: str
    published_date: str
    duration_sec: int
    source_audio_path: Path
    transcript: TranscriptionResult
    path: Path

    def to_dict(self) -> dict:
        return {
            "podcast": self.podcast,
            "episode_title": self.episode_title,
            "published_date": self.published_date,
            "duration_sec": self.duration_sec,
            "source_audio_path": str(self.source_audio_path),
            "transcript": self.transcript.to_dict(),
        }


__all__ = ["Podcast", "Subscription", "TranscriptionResult", "Episode"]
