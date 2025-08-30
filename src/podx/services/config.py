"""Application configuration models and loader.

This module defines the :class:`Config` dataclass along with related
settings structures.  Configuration is loaded from a YAML (or JSON) file via
``load_config``.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
import json
import os

try:  # pragma: no cover
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


@dataclass
class WhisperSettings:
    runner: str
    model: str
    extra_args: list[str]


@dataclass
class LoggingSettings:
    level: str = "INFO"
    file_max_mb: int = 5


@dataclass
class UiSettings:
    window_width: int = 1400
    window_height: int = 800
    # Episodes view splitters
    episodes_vertical_splitter: list[int] = field(default_factory=list)
    episodes_horizontal_splitter: list[int] = field(default_factory=list)


@dataclass
class Config:
    root_dir: Path
    whisper: WhisperSettings
    logging: LoggingSettings
    save_audio_copy: bool = False
    ui: UiSettings = field(default_factory=UiSettings)


def load_config(path: Path | None = None) -> Config:
    """Load configuration from YAML file."""
    if path is None:
        env = os.environ.get("PODX_CONFIG")
        if env:
            path = Path(env)
        else:
            path = Path.home() / ".podx" / "config.yaml"
    if path.exists():
        text = path.read_text()
        data = yaml.safe_load(text) if yaml else json.loads(text)
    else:
        data = {}
    whisper = data.get("whisper", {})
    logging = data.get("logging", {})
    ui = data.get("ui", {})
    return Config(
        root_dir=Path(data.get("root_dir", "./podx")),
        whisper=WhisperSettings(
            runner=whisper.get("runner", "mlx"),
            model=whisper.get("model", "mlx-community/whisper-small-mlx-q4"),
            extra_args=list(whisper.get("extra_args", [])),
        ),
        logging=LoggingSettings(
            level=logging.get("level", "INFO"),
            file_max_mb=int(logging.get("file_max_mb", 5)),
        ),
        save_audio_copy=bool(data.get("save_audio_copy", False)),
        ui=UiSettings(
            window_width=int(ui.get("window_width", 1400)),
            window_height=int(ui.get("window_height", 800)),
            episodes_vertical_splitter=list(ui.get("episodes_vertical_splitter", [])),
            episodes_horizontal_splitter=list(ui.get("episodes_horizontal_splitter", [])),
        ),
    )


def save_config(cfg: Config, path: Path | None = None) -> None:
    """Persist configuration to YAML (preferred) or JSON.

    This overwrites the file while keeping only known fields.
    """
    if path is None:
        env = os.environ.get("PODX_CONFIG")
        if env:
            path = Path(env)
        else:
            path = Path.home() / ".podx" / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "root_dir": str(cfg.root_dir),
        "whisper": asdict(cfg.whisper),
        "logging": asdict(cfg.logging),
        "save_audio_copy": cfg.save_audio_copy,
        "ui": asdict(cfg.ui),
    }
    text = yaml.safe_dump(data, sort_keys=False) if yaml else json.dumps(data, indent=2)
    path.write_text(text)


__all__ = [
    "Config",
    "WhisperSettings",
    "LoggingSettings",
    "UiSettings",
    "load_config",
    "save_config",
]

