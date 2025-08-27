from __future__ import annotations

from typing import List, Protocol
from urllib import parse, request
import json
from podx.services.config import Config
from ..models import PodcastSearchResult


class DirectoryClient(Protocol):
    """Abstract podcast directory search client."""

    def search(self, term: str) -> List[PodcastSearchResult]:
        ...


class ITunesDirectoryClient:
    """Thin wrapper around the Apple iTunes Search API."""

    base_url = "https://itunes.apple.com/search"

    def search(self, term: str) -> List[PodcastSearchResult]:
        params = {"media": "podcast", "term": term}
        url = f"{self.base_url}?{parse.urlencode(params)}"
        with request.urlopen(url) as resp:
            data = json.load(resp)
        podcasts: list[PodcastSearchResult] = []
        for item in data.get("results", []):
            name = item.get("collectionName") or item.get("trackName")
            feed_url = item.get("feedUrl")
            genres = item.get("genres", [])
            # Optional rich fields
            icon_url = (
                item.get("artworkUrl600")
                or item.get("artworkUrl100")
                or item.get("artworkUrl60")
            )
            publisher = item.get("artistName")
            url = item.get("collectionViewUrl") or item.get("trackViewUrl")
            if name and feed_url:
                podcasts.append(
                    PodcastSearchResult(
                        name=name,
                        feed_url=feed_url,
                        genres=list(genres),
                        icon_url=icon_url,
                        publisher=publisher,
                        url=url,
                    )
                )
        return podcasts


class DirectoryService:
    """Service for searching podcast directories."""

    def __init__(self, cfg: Config, client: DirectoryClient | None = None) -> None:
        self.cfg = cfg
        self.client = client or ITunesDirectoryClient()

    def search_podcasts(self, term: str) -> List[PodcastSearchResult]:
        return self.client.search(term)


__all__ = [
    "PodcastSearchResult",
    "DirectoryClient",
    "ITunesDirectoryClient",
    "DirectoryService",
    "request",
]
