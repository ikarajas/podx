from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from ..models import Episode, Podcast

if TYPE_CHECKING:  # pragma: no cover
    from .ingestion import IngestionService
    from .directory import DirectoryService, DirectoryClient, ITunesDirectoryClient

__all__ = [
    "Episode",
    "Podcast",
    "IngestionService",
    "DirectoryService",
    "DirectoryClient",
    "ITunesDirectoryClient",
]


def __getattr__(name: str):  # pragma: no cover - simple forwarding
    if name in {"IngestionService"}:
        module = import_module(".ingestion", __name__)
        return getattr(module, name)
    if name in {"DirectoryService", "DirectoryClient", "ITunesDirectoryClient"}:
        module = import_module(".directory", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__} has no attribute {name}")
