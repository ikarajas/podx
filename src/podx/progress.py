from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class ProgressReporter:
    """Strategy for emitting progress updates.

    Implementations should keep output concerns separate from ingestion/runner.
    """

    def on_update(self, percent: int, current_sec: int, total_sec: int) -> None:  # pragma: no cover - simple IO
        pass

    def on_done(self) -> None:  # pragma: no cover - simple IO
        pass


class ConsoleProgressReporter(ProgressReporter):
    def __init__(self) -> None:
        self._last_printed: Optional[int] = None

    def on_update(self, percent: int, current_sec: int, total_sec: int) -> None:  # pragma: no cover - simple IO
        # Only print when percent meaningfully advances to avoid noise
        if self._last_printed is None or percent - self._last_printed >= 5 or percent in (0, 100):
            print(f"Transcribing: {percent:3d}% ({current_sec}/{total_sec}s)")
            self._last_printed = percent

    def on_done(self) -> None:  # pragma: no cover - simple IO
        # Ensure a final newline or marker if needed
        if self._last_printed != 100:
            print("Transcribing: 100%")


class QtProgressReporter(ProgressReporter):
    """Placeholder reporter that emits Qt style signals.

    The ``update_signal`` and ``done_signal`` callables are intended to be
    connected to Qt ``Signal`` objects in a GUI application.  They default to
    ``None`` so the reporter is a no-op when used outside of a Qt context.
    """

    def __init__(
        self,
        update_signal: Optional[Callable[[int, int, int], None]] = None,
        done_signal: Optional[Callable[[], None]] = None,
    ) -> None:
        self.update_signal = update_signal
        self.done_signal = done_signal

    def on_update(self, percent: int, current_sec: int, total_sec: int) -> None:  # pragma: no cover - simple IO
        if self.update_signal is not None:
            self.update_signal(percent, current_sec, total_sec)

    def on_done(self) -> None:  # pragma: no cover - simple IO
        if self.done_signal is not None:
            self.done_signal()


_TIMECODE_RE = re.compile(
    # Matches [HH:MM:SS.mmm --> HH:MM:SS.mmm] or [MM:SS.mmm --> MM:SS.mmm]
    r"\[(?:(?P<s_h>\d+):)?(?P<s_m>\d{1,2}):(?P<s_s>\d{2})\.(?P<s_ms>\d{3})\s*--\>\s*"
    r"(?:(?P<e_h>\d+):)?(?P<e_m>\d{1,2}):(?P<e_s>\d{2})\.(?P<e_ms>\d{3})\]"
)


def _hms_to_seconds(h: Optional[str], m: str, s: str, ms: str) -> float:
    hours = int(h or 0)
    minutes = int(m)
    seconds = int(s)
    millis = int(ms)
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def parse_end_seconds(line: str) -> Optional[float]:
    """Return the end time in seconds from a mlx_whisper timestamp line.

    Example line: "[00:03.000 --> 00:05.000]  text" or "[01:00:00.000 --> 01:00:02.000]".
    """
    m = _TIMECODE_RE.search(line)
    if not m:
        return None
    return _hms_to_seconds(m.group("e_h"), m.group("e_m"), m.group("e_s"), m.group("e_ms"))


class ProgressFeeder:
    """Feed stdout lines to compute progress and notify a reporter.

    Keeps state across lines; call `consume_line` for each output line.
    """

    def __init__(self, total_duration_sec: int, reporter: ProgressReporter, step: int = 5) -> None:
        self.total = max(0, int(total_duration_sec))
        self.reporter = reporter
        self.step = max(1, int(step))
        self._last_percent = -1
        self._last_sec = 0

    def consume_line(self, line: str) -> None:
        end_s = parse_end_seconds(line)
        if end_s is None or self.total <= 0:
            return
        self._last_sec = int(end_s)
        pct = min(100, int((end_s / self.total) * 100))
        if pct > self._last_percent and (pct % self.step == 0 or pct in (0, 100)):
            self.reporter.on_update(pct, self._last_sec, self.total)
            self._last_percent = pct

    def done(self) -> None:
        if self.total > 0:
            if self._last_sec >= self.total and self._last_percent < 100:
                self.reporter.on_update(100, self.total, self.total)
        self.reporter.on_done()
