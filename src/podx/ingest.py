from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from .config import Config, load_config

try:  # pragma: no cover
    from mutagen import File as MutagenFile  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    MutagenFile = None


def extract_metadata(audio_path: Path) -> dict:
    meta: dict[str, Optional[str | int]] = {
        "podcast": None,
        "episode_title": None,
        "published_date": date.today().isoformat(),
        "duration_sec": 0,
    }
    if MutagenFile is None:
        return meta
    audio = MutagenFile(audio_path)
    if audio is None:
        return meta
    tags = getattr(audio, "tags", {}) or {}
    podcast = tags.get("album") or tags.get("TALB")
    if podcast:
        meta["podcast"] = podcast[0] if isinstance(podcast, list) else str(podcast)
    title = tags.get("title") or tags.get("TIT2")
    if title:
        meta["episode_title"] = title[0] if isinstance(title, list) else str(title)
    date_tag = tags.get("date") or tags.get("TDRC")
    if date_tag:
        value = date_tag[0] if isinstance(date_tag, list) else str(date_tag)
        meta["published_date"] = str(value)[:10]
    info = getattr(audio, "info", None)
    if info and hasattr(info, "length"):
        meta["duration_sec"] = int(info.length)
    return meta


def ingest_episode(
    audio: Path,
    podcast: Optional[str] = None,
    episode: Optional[str] = None,
    force: bool = False,
    cfg: Config | None = None,
) -> int:
    """Backward compatible wrapper around :class:`IngestionService`.

    This function retains the original command line behaviour by delegating to
    :class:`podx.services.IngestionService`.  An exit code is returned and
    messages are printed to stdout.
    """

    from .services import IngestionService
    from .progress import ConsoleProgressWriter

    service = IngestionService(cfg or load_config())
    try:
        result = service.ingest_episode(
            audio, podcast, episode, force, ConsoleProgressWriter()
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


def _language_from_args(args: list[str]) -> str:
    if "--language" in args:
        idx = args.index("--language")
        if idx + 1 < len(args):
            return args[idx + 1]
    return "en"


__all__ = ["ingest_episode"]
