from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .ingestion import Episode, IngestionService
    from .directory import (
        Podcast,
        DirectoryService,
        DirectoryClient,
        ITunesDirectoryClient,
    )

__all__ = [
    "Episode",
    "IngestionService",
    "Podcast",
    "DirectoryService",
    "DirectoryClient",
    "ITunesDirectoryClient",
]


def __getattr__(name: str):  # pragma: no cover - simple forwarding
    if name in {"Episode", "IngestionService"}:
        module = import_module(".ingestion", __name__)
        return getattr(module, name)
    if name in {"Podcast", "DirectoryService", "DirectoryClient", "ITunesDirectoryClient"}:
        module = import_module(".directory", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__} has no attribute {name}")
