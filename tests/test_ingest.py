import wave
from pathlib import Path
import sys
import pytest
import json as jsonlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from podx.services import IngestionService
from podx.app import get_config


def create_audio(path: Path) -> None:
    with wave.open(str(path), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)


def config_file(tmp_path: Path) -> Path:
    cfg = {
        "root_dir": str(tmp_path / "root"),
        "whisper": {"runner": "mlx", "model": "small.en", "extra_args": ["--language", "en"]},
        "logging": {"level": "INFO", "file_max_mb": 5},
    }
    path = tmp_path / "config.yaml"
    path.write_text(jsonlib.dumps(cfg))
    return path


def fake_metadata(_path: Path):
    return {
        "podcast": None,
        "episode_title": None,
        "published_date": "2025-08-01",
        "duration_sec": 1,
    }


def fake_transcribe(self, audio_path, vtt_path, txt_path, log_file):
    vtt_path.write_text("WEBVTT\n\n00:00.000 --> 00:01.000\nHello\n")
    txt_path.write_text("Hello")
    Path(log_file).write_text("log")


def test_ingest_creates_structure(tmp_path, monkeypatch):
    cfg = config_file(tmp_path)
    monkeypatch.setenv("PODX_CONFIG", str(cfg))
    get_config.cache_clear()
    audio = tmp_path / "audio.wav"
    create_audio(audio)
    monkeypatch.setattr("podx.services.ingestion.extract_metadata", fake_metadata)
    monkeypatch.setattr("podx.whisper.WhisperRunner.transcribe", fake_transcribe)
    service = IngestionService(get_config())
    episode = service.ingest_episode(audio, "Test Pod", "Ep1")
    assert episode is not None
    episode_dir = tmp_path / "root" / "Test Pod" / "2025-08-01 - Ep1"
    assert episode.path == episode_dir
    # By default we do not keep a copy of the audio in the episode directory
    assert not (episode_dir / "audio.wav").exists()
    assert episode.transcript.vtt_path.exists()
    assert episode.transcript.txt_path.exists()
    assert episode.podcast == "Test Pod"
    assert episode.transcript.status == "done"


def test_ingest_skips_existing_transcript(tmp_path, monkeypatch):
    cfg = config_file(tmp_path)
    monkeypatch.setenv("PODX_CONFIG", str(cfg))
    get_config.cache_clear()
    audio = tmp_path / "audio.wav"
    create_audio(audio)
    monkeypatch.setattr("podx.services.ingestion.extract_metadata", fake_metadata)
    monkeypatch.setattr("podx.whisper.WhisperRunner.transcribe", fake_transcribe)
    service = IngestionService(get_config())
    service.ingest_episode(audio, "Test Pod", "Ep1")
    called = False

    def fail_transcribe(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("podx.whisper.WhisperRunner.transcribe", fail_transcribe)
    result = service.ingest_episode(audio, "Test Pod", "Ep1")
    assert result is None
    assert called is False


def test_ingest_bad_audio(tmp_path, monkeypatch):
    cfg = config_file(tmp_path)
    monkeypatch.setenv("PODX_CONFIG", str(cfg))
    get_config.cache_clear()
    audio = tmp_path / "audio.wav"
    create_audio(audio)
    monkeypatch.setattr("podx.services.ingestion.extract_metadata", fake_metadata)

    def bad_transcribe(*args, **kwargs):
        raise RuntimeError("fail")

    monkeypatch.setattr("podx.whisper.WhisperRunner.transcribe", bad_transcribe)
    service = IngestionService(get_config())
    with pytest.raises(RuntimeError):
        service.ingest_episode(audio, "Test Pod", "Ep1")
    episode_dir = tmp_path / "root" / "Test Pod" / "2025-08-01 - Ep1"
    assert not (episode_dir / "transcript.vtt").exists()
    assert not (episode_dir / "episode.json").exists()


def test_ingest_keeps_audio_when_enabled(tmp_path, monkeypatch):
    # Enable audio copy in config
    cfg = {
        "root_dir": str(tmp_path / "root"),
        "whisper": {"runner": "mlx", "model": "small.en", "extra_args": ["--language", "en"]},
        "logging": {"level": "INFO", "file_max_mb": 5},
        "save_audio_copy": True,
    }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(jsonlib.dumps(cfg))
    monkeypatch.setenv("PODX_CONFIG", str(cfg_path))
    get_config.cache_clear()

    audio = tmp_path / "audio.wav"
    create_audio(audio)
    monkeypatch.setattr("podx.services.ingestion.extract_metadata", fake_metadata)
    monkeypatch.setattr("podx.whisper.WhisperRunner.transcribe", fake_transcribe)
    service = IngestionService(get_config())
    episode = service.ingest_episode(audio, "Test Pod", "Ep1")
    assert episode is not None
    episode_dir = tmp_path / "root" / "Test Pod" / "2025-08-01 - Ep1"
    assert (episode_dir / "audio.wav").exists()
    assert episode.transcript.vtt_path.exists()
    assert episode.transcript.txt_path.exists()
