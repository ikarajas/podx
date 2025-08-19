from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
import json
import os
import shutil
from pathlib import Path
from typing import Optional

from ..config import Config, load_config
from ..progress import ProgressReporter
from ..whisper import get_runner

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
    audio = MutagenFile(audio_path, easy=True)
    if audio is None:
        return meta
    tags = getattr(audio, "tags", {}) or {}
    podcast = tags.get("album")
    if podcast:
        meta["podcast"] = podcast[0] if isinstance(podcast, list) else str(podcast)
    title = tags.get("title")
    if title:
        meta["episode_title"] = title[0] if isinstance(title, list) else str(title)
    date_tag = tags.get("date")
    if date_tag:
        value = date_tag[0] if isinstance(date_tag, list) else str(date_tag)
        meta["published_date"] = str(value)[:10]
    info = getattr(audio, "info", None)
    if info and hasattr(info, "length"):
        meta["duration_sec"] = int(info.length)
    return meta


def _language_from_args(args: list[str]) -> str:
    if "--language" in args:
        idx = args.index("--language")
        if idx + 1 < len(args):
            return args[idx + 1]
    return "en"


@dataclass
class Episode:
    """Represents an ingested podcast episode."""

    podcast: str
    episode_title: str
    published_date: str
    duration_sec: int
    source_audio_path: str
    transcript: dict
    path: Path


class IngestionService:
    """Service responsible for ingesting podcast episodes."""

    def __init__(self, cfg: Config | None = None) -> None:
        self.cfg = cfg or load_config()

    def ingest_episode(
        self,
        audio: Path,
        podcast: Optional[str] = None,
        episode: Optional[str] = None,
        force: bool = False,
        reporter: ProgressReporter | None = None,
    ) -> Episode | None:
        """Ingest ``audio`` and return an :class:`Episode`.

        ``None`` is returned when a transcript already exists and ``force`` is
        not specified.  Errors raise ``RuntimeError``.
        """

        audio = audio.resolve()
        if not audio.exists():
            raise FileNotFoundError("Audio file not found")

        meta = extract_metadata(audio)
        podcast_name = podcast or meta.get("podcast") or "Unknown Podcast"
        episode_title = episode or meta.get("episode_title") or audio.stem
        published_date = meta.get("published_date")
        duration_sec = meta.get("duration_sec", 0)

        root_dir = self.cfg.root_dir
        episode_dir = root_dir / podcast_name / f"{published_date} - {episode_title}"
        transcript_vtt = episode_dir / "transcript.vtt"
        transcript_txt = episode_dir / "transcript.txt"
        lock_path = episode_dir / ".lock"

        if transcript_vtt.exists() and not force:
            # Nothing to do – return ``None`` to signal skip.
            return None

        episode_dir.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError as exc:  # pragma: no cover - race condition
            raise RuntimeError("Episode is locked; try again later.") from exc

        tmp_dir = episode_dir / "tmp"
        logs_dir = episode_dir / "logs"
        tmp_dir.mkdir(exist_ok=True)
        logs_dir.mkdir(exist_ok=True)
        log_file = logs_dir / "transcribe.log"

        runner = get_runner(self.cfg.whisper)
        tmp_audio = tmp_dir / audio.name
        tmp_vtt = tmp_dir / "transcript.vtt"
        tmp_txt = tmp_dir / "transcript.txt"
        shutil.copy2(audio, tmp_audio)
        try:
            # Stream progress if supported and reporter provided
            transcribe_kwargs: dict = {}
            try:
                import inspect

                sig = inspect.signature(runner.transcribe)
                if reporter is not None and "reporter" in sig.parameters:
                    transcribe_kwargs["reporter"] = reporter
                if (
                    "total_duration_sec" in sig.parameters
                    and isinstance(duration_sec, int)
                    and duration_sec > 0
                ):
                    transcribe_kwargs["total_duration_sec"] = duration_sec
            except Exception:  # pragma: no cover - defensive
                pass

            runner.transcribe(tmp_audio, tmp_vtt, tmp_txt, log_file, **transcribe_kwargs)

            # Optionally persist a copy of the source audio in the episode directory
            if self.cfg.save_audio_copy:
                shutil.move(str(tmp_audio), episode_dir / audio.name)
            shutil.move(str(tmp_vtt), transcript_vtt)
            shutil.move(str(tmp_txt), transcript_txt)
            shutil.rmtree(tmp_dir)

            transcript = {
                "status": "done",
                "engine": self.cfg.whisper.runner,
                "model": self.cfg.whisper.model,
                "language": _language_from_args(self.cfg.whisper.extra_args),
                "created_at": datetime.now().isoformat(),
                "files": ["transcript.vtt", "transcript.txt"],
            }

            episode_data = Episode(
                podcast=podcast_name,
                episode_title=episode_title,
                published_date=published_date,
                duration_sec=duration_sec,
                source_audio_path=str(audio),
                transcript=transcript,
                path=episode_dir,
            )

            episode_json = {
                "podcast": podcast_name,
                "episode_title": episode_title,
                "published_date": published_date,
                "duration_sec": duration_sec,
                "source_audio_path": str(audio),
                "transcript": transcript,
            }
            with open(episode_dir / "episode.json", "w") as f:
                json.dump(episode_json, f, indent=2)
            return episode_data
        except Exception as exc:
            # Failure – clean up any partially written files.
            shutil.rmtree(tmp_dir, ignore_errors=True)
            for p in (transcript_vtt, transcript_txt, episode_dir / audio.name):
                if p.exists():
                    p.unlink()
            raise RuntimeError(f"Error during transcription: {exc}") from exc
        finally:
            if lock_path.exists():
                lock_path.unlink()


__all__ = ["Episode", "IngestionService"]
