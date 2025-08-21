"""Backward compatibility wrapper for :class:`IngestionService`.

This module preserves the old ``podx.ingest.ingest_episode`` API while
delegating to :class:`podx.services.IngestionService`.  A ``DeprecationWarning``
is emitted on use.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import TYPE_CHECKING

from podx.services.config import Config
from .app import get_config
from .services import IngestionService

if TYPE_CHECKING:  # pragma: no cover - typing only
    from podx.services.progress import ProgressReporter


def ingest_episode(
    audio: Path,
    podcast: str | None = None,
    episode: str | None = None,
    force: bool = False,
    cfg: Config | None = None,
    reporter: "ProgressReporter" | None = None,
):
    """Delegate to :meth:`IngestionService.ingest_episode`.

    Parameters mirror :meth:`IngestionService.ingest_episode`.  The return value
    is whatever the service returns.  ``DeprecationWarning`` is issued to signal
    that this wrapper will be removed in a future release.
    """

    warnings.warn(
        "podx.ingest.ingest_episode is deprecated; use IngestionService directly",
        DeprecationWarning,
        stacklevel=2,
    )
    service = IngestionService(cfg or get_config())
    return service.ingest_episode(audio, podcast, episode, force, reporter)


__all__ = ["ingest_episode"]

