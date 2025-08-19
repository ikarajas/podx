from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol
from urllib import parse, request
import json


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


def search_podcasts(term: str, client: DirectoryClient | None = None) -> List[Podcast]:
    """Search for podcasts by name using the configured directory client."""

    directory = client or ITunesDirectoryClient()
    return directory.search(term)


__all__ = ["Podcast", "DirectoryClient", "ITunesDirectoryClient", "search_podcasts"]
