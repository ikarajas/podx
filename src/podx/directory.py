from __future__ import annotations

from typing import List

from .services.directory import (
    Podcast,
    DirectoryClient,
    ITunesDirectoryClient,
    DirectoryService,
    request,
)


def search_podcasts(term: str, client: DirectoryClient | None = None) -> List[Podcast]:
    """Backward compatible wrapper around :class:`DirectoryService`."""

    service = DirectoryService(client)
    return service.search_podcasts(term)


__all__ = ["Podcast", "DirectoryClient", "ITunesDirectoryClient", "search_podcasts", "request"]
