"""Fallback stub to gracefully handle missing PyQt6 system libraries.

This stub attempts to import the real PyQt6 package. If that fails (for
example due to missing libGL), an ImportError is raised so callers can
skip optional Qt tests.
"""
from __future__ import annotations

import importlib
import sys

_orig = list(sys.path)
try:
    sys.path = _orig[1:]
    real = importlib.import_module("PyQt6")
    # Attempt to import a common submodule; if this fails we know Qt
    # libraries are missing and should propagate ImportError.
    importlib.import_module("PyQt6.QtCore")
except Exception as exc:  # pragma: no cover - depends on environment
    raise ImportError(str(exc))
finally:  # pragma: no cover - depends on environment
    sys.path = _orig

globals().update(real.__dict__)
