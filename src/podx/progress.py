from __future__ import annotations

from warnings import warn

from podx.services.progress import (
    ProgressReporter,
    ConsoleProgressReporter,
    QtProgressReporter,
    parse_end_seconds,
    ProgressFeeder,
)

warn(
    "podx.progress is deprecated; use podx.services.progress instead",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "ProgressReporter",
    "ConsoleProgressReporter",
    "QtProgressReporter",
    "parse_end_seconds",
    "ProgressFeeder",
]
