from __future__ import annotations

from typing import List

from podx.services.config import Config
from .app import get_config
from .services.directory import (
    Podcast,
    DirectoryClient,
    ITunesDirectoryClient,
    DirectoryService,
    request,
)


def search_podcasts(
    term: str, client: DirectoryClient | None = None, cfg: Config | None = None
) -> List[Podcast]:
    """Backward compatible wrapper around :class:`DirectoryService`."""

    service = DirectoryService(cfg or get_config(), client)
    return service.search_podcasts(term)


__all__ = ["Podcast", "DirectoryClient", "ITunesDirectoryClient", "search_podcasts", "request"]
