"""Deprecated configuration module.

This module is a thin shim that re-exports the configuration dataclasses and
``load_config`` from :mod:`podx.services.config`.  Importing from here will emit
``DeprecationWarning`` to encourage callers to migrate.
"""

from __future__ import annotations

from warnings import warn

from .services.config import (
    Config,
    LoggingSettings,
    WhisperSettings,
    load_config,
)

warn(
    "podx.config is deprecated; use podx.services.config",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["Config", "LoggingSettings", "WhisperSettings", "load_config"]

