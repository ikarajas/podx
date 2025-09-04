"""Fallback stub to gracefully handle missing PyQt6 system libraries.

This stub attempts to import the real PyQt6 package. If that fails (for
example due to missing libGL), an ImportError is raised so callers can
skip optional Qt tests.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

# When this stub is imported as "PyQt6", attempting to import the real package
# via importlib will usually return this stub again due to sys.modules caching.
# To reliably delegate, temporarily remove paths that point to the project
# "src" directory containing this stub and pop the current module from
# sys.modules before importing the real package.

_orig_path = list(sys.path)
_orig_mod = sys.modules.get("PyQt6")
try:
    # Build a sys.path without any entry that looks like a project "src"
    # directory containing this stub (i.e., where a "PyQt6" subdir exists).
    filtered: list[str] = []
    for p in _orig_path:
        try:
            pp = Path(p)
            if pp.name == "src" and (pp / "PyQt6").exists():
                continue
        except Exception:  # pragma: no cover - defensive
            pass
        filtered.append(p)
    sys.path = filtered
    # Remove this stub from sys.modules so import resolves to the real package.
    try:
        if "PyQt6" in sys.modules:
            del sys.modules["PyQt6"]
    except Exception:  # pragma: no cover - defensive
        pass
    real = importlib.import_module("PyQt6")
    # Validate that QtCore is present; if this fails, surface ImportError so
    # callers can decide whether to skip UI functionality/tests.
    importlib.import_module("PyQt6.QtCore")
except Exception as exc:  # pragma: no cover - depends on environment
    # Restore module cache on failure to avoid leaving a half-initialised state
    if _orig_mod is not None:
        sys.modules["PyQt6"] = _orig_mod
    raise ImportError(str(exc))
finally:  # pragma: no cover - depends on environment
    sys.path = _orig_path

# Expose attributes of the real package through this stub module
globals().update(real.__dict__)
