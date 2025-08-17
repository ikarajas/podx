from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from datetime import datetime, date
from typing import Optional

from .config import Config, load_config
from .whisper import get_runner
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
    cfg = cfg or load_config()
    audio = audio.resolve()
    if not audio.exists():
        print("Audio file not found")
        return 1

    meta = extract_metadata(audio)
    podcast = podcast or meta.get("podcast") or "Unknown Podcast"
    episode_title = episode or meta.get("episode_title") or audio.stem
    published_date = meta.get("published_date")
    duration_sec = meta.get("duration_sec", 0)

    root_dir = cfg.root_dir
    episode_dir = root_dir / podcast / f"{published_date} - {episode_title}"
    transcript_vtt = episode_dir / "transcript.vtt"
    transcript_txt = episode_dir / "transcript.txt"
    lock_path = episode_dir / ".lock"

    if transcript_vtt.exists() and not force:
        print("Transcript already exists, nothing to do.")
        return 0

    episode_dir.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        print("Episode is locked; try again later.")
        return 1

    tmp_dir = episode_dir / "tmp"
    logs_dir = episode_dir / "logs"
    tmp_dir.mkdir(exist_ok=True)
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / "transcribe.log"

    runner = get_runner(cfg.whisper)
    tmp_audio = tmp_dir / audio.name
    tmp_vtt = tmp_dir / "transcript.vtt"
    tmp_txt = tmp_dir / "transcript.txt"
    shutil.copy2(audio, tmp_audio)
    try:
        runner.transcribe(tmp_audio, tmp_vtt, tmp_txt, log_file)
        shutil.move(str(tmp_audio), episode_dir / audio.name)
        shutil.move(str(tmp_vtt), transcript_vtt)
        shutil.move(str(tmp_txt), transcript_txt)
        shutil.rmtree(tmp_dir)
        episode_json = {
            "podcast": podcast,
            "episode_title": episode_title,
            "published_date": published_date,
            "duration_sec": duration_sec,
            "source_audio_path": str(audio),
            "transcript": {
                "status": "done",
                "engine": cfg.whisper.runner,
                "model": cfg.whisper.model,
                "language": _language_from_args(cfg.whisper.extra_args),
                "created_at": datetime.now().isoformat(),
                "files": ["transcript.vtt", "transcript.txt"],
            },
        }
        with open(episode_dir / "episode.json", "w") as f:
            json.dump(episode_json, f, indent=2)
        return 0
    except Exception as exc:  # pragma: no cover - exception branch tested
        print(f"Error during transcription: {exc}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        for p in (transcript_vtt, transcript_txt, episode_dir / audio.name):
            if p.exists():
                p.unlink()
        return 1
    finally:
        if lock_path.exists():
            lock_path.unlink()


def _language_from_args(args: list[str]) -> str:
    if "--language" in args:
        idx = args.index("--language")
        if idx + 1 < len(args):
            return args[idx + 1]
    return "en"


__all__ = ["ingest_episode"]
