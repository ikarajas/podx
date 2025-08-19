from __future__ import annotations

from pathlib import Path
from typing import Optional

from .config import Config
from .app import get_config
from .progress import ProgressReporter


def ingest_episode(
    audio: Path,
    podcast: Optional[str] = None,
    episode: Optional[str] = None,
    force: bool = False,
    cfg: Config | None = None,
    reporter: ProgressReporter | None = None,
) -> int:
    """Backward compatible wrapper around :class:`IngestionService`.

    This function retains the original command line behaviour by delegating to
    :class:`podx.services.IngestionService`.  An exit code is returned and
    messages are printed to stdout.
    """

    from .services import IngestionService
    from .progress import ConsoleProgressReporter

    service = IngestionService(cfg or get_config())
    reporter = reporter or ConsoleProgressReporter()
    try:
        result = service.ingest_episode(
            audio, podcast, episode, force, reporter
        )
        if result is None:
            print("Transcript already exists, nothing to do.")
        return 0
    except FileNotFoundError:
        print("Audio file not found")
        return 1
    except Exception as exc:  # pragma: no cover - exception branch tested
        print(str(exc))
        return 1


__all__ = ["ingest_episode"]
