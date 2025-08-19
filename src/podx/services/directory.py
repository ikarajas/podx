from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol
from urllib import parse, request
import json
from ..config import Config


@dataclass
class Podcast:
    """Simple representation of a podcast in a directory search result."""

    name: str
    feed_url: str
    genres: list[str]


class DirectoryClient(Protocol):
    """Abstract podcast directory search client."""

    def search(self, term: str) -> List[Podcast]:
        ...


class ITunesDirectoryClient:
    """Thin wrapper around the Apple iTunes Search API."""

    base_url = "https://itunes.apple.com/search"

    def search(self, term: str) -> List[Podcast]:
        params = {"media": "podcast", "term": term}
        url = f"{self.base_url}?{parse.urlencode(params)}"
        with request.urlopen(url) as resp:
            data = json.load(resp)
        podcasts: list[Podcast] = []
        for item in data.get("results", []):
            name = item.get("collectionName") or item.get("trackName")
            feed_url = item.get("feedUrl")
            genres = item.get("genres", [])
            if name and feed_url:
                podcasts.append(Podcast(name=name, feed_url=feed_url, genres=list(genres)))
        return podcasts


class DirectoryService:
    """Service for searching podcast directories."""

    def __init__(self, cfg: Config, client: DirectoryClient | None = None) -> None:
        self.cfg = cfg
        self.client = client or ITunesDirectoryClient()

    def search_podcasts(self, term: str) -> List[Podcast]:
        return self.client.search(term)


__all__ = [
    "Podcast",
    "DirectoryClient",
    "ITunesDirectoryClient",
    "DirectoryService",
    "request",
]
