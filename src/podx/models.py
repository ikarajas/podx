from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class PodcastSearchResult:
    """Representation of a podcast returned by a directory search.

    Optional fields allow richer detail views without forcing all
    directories to provide them.
    """

    name: str
    feed_url: str
    genres: list[str]
    # Optional details for richer UI
    icon_url: str | None = None
    publisher: str | None = None
    url: str | None = None  # Directory page URL


@dataclass
class Subscription:
    """Represents a subscribed podcast."""

    name: str
    feed_url: str
    icon_url: str | None = None


@dataclass
class FeedEpisode:
    """Episode metadata parsed from an RSS feed."""

    title: str
    description: str
    published: datetime | None
    duration: int | None
    artwork_url: str | None
    transcribed: bool = False


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


__all__ = [
    "PodcastSearchResult",
    "Subscription",
    "FeedEpisode",
    "TranscriptionResult",
    "Episode",
]
