from __future__ import annotations

import warnings

from podx.services.whisper import WhisperRunner, get_runner

warnings.warn(
    "podx.whisper is deprecated; use podx.services.whisper instead",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["WhisperRunner", "get_runner"]
