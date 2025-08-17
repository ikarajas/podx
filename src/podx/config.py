from __future__ import annotations

from dataclasses import dataclass
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
class Config:
    root_dir: Path
    whisper: WhisperSettings
    logging: LoggingSettings


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
    return Config(
        root_dir=Path(data.get("root_dir", "./podx")),
        whisper=WhisperSettings(
            runner=whisper.get("runner", "mlx"),
            model=whisper.get("model", "small.en"),
            extra_args=list(whisper.get("extra_args", [])),
        ),
        logging=LoggingSettings(
            level=logging.get("level", "INFO"),
            file_max_mb=int(logging.get("file_max_mb", 5)),
        ),
    )
