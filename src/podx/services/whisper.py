from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional
import os

from podx.services.config import WhisperSettings
from podx.services.progress import ProgressFeeder, ProgressReporter


def _language_from_args(args: list[str]) -> Optional[str]:
    try:
        if "--language" in args:
            i = args.index("--language")
            if i + 1 < len(args):
                return args[i + 1]
    except Exception:
        pass
    return None


def _fmt_ts(s: float) -> str:
    ms = int(round((s - int(s)) * 1000))
    s_int = int(s)
    h = s_int // 3600
    m = (s_int % 3600) // 60
    sec = s_int % 60
    return f"{h:02d}:{m:02d}:{sec:02d}.{ms:03d}"


class WhisperRunner:
    def __init__(self, settings: WhisperSettings):
        self.settings = settings
        self._executor: ThreadPoolExecutor | None = None

    def _get_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1)
        return self._executor

    def transcribe_async(
        self,
        audio_path: Path,
        vtt_path: Path,
        txt_path: Path,
        log_file: Path,
        *,
        reporter: Optional[ProgressReporter] = None,
        total_duration_sec: Optional[int] = None,
        done_callback: Optional[Callable[[Future], None]] = None,
    ) -> Future:
        executor = self._get_executor()
        kwargs = {}
        if reporter is not None:
            kwargs["reporter"] = reporter
        if total_duration_sec is not None:
            kwargs["total_duration_sec"] = total_duration_sec
        future = executor.submit(
            self.transcribe,
            audio_path,
            vtt_path,
            txt_path,
            log_file,
            **kwargs,
        )
        if done_callback is not None:
            future.add_done_callback(done_callback)
        return future

    def transcribe(
        self,
        audio_path: Path,
        vtt_path: Path,
        txt_path: Path,
        log_file: Path,
        *,
        reporter: Optional[ProgressReporter] = None,
        total_duration_sec: Optional[int] = None,
    ) -> None:
        """Run Whisper via Python libraries to produce VTT and TXT transcripts.

        Engines (all Python APIs, no shelling out):
        - "faster": faster-whisper
        - "mlx": mlx_whisper (falls back to faster-whisper if unavailable)
        - "whisper"/"openai": openai-whisper Python package
        """
        runner = (self.settings.runner or "").lower()

        # Ensure target directory exists
        output_dir = vtt_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        if runner == "faster":
            try:
                from faster_whisper import WhisperModel  # type: ignore
            except Exception as exc:  # pragma: no cover - optional dep
                raise RuntimeError(
                    "The 'faster' runner requires faster-whisper. Install with 'pip install faster-whisper' or 'pip install .[faster]'."
                ) from exc

            language = None
            if "--language" in self.settings.extra_args:
                i = self.settings.extra_args.index("--language")
                if i + 1 < len(self.settings.extra_args):
                    language = self.settings.extra_args[i + 1]

            compute_type = os.environ.get("PODX_FASTER_COMPUTE", "int8")
            device = os.environ.get("PODX_FASTER_DEVICE", "auto")

            model = WhisperModel(self.settings.model or "small.en", device=device, compute_type=compute_type)

            feeder: Optional[ProgressFeeder] = None
            if reporter is not None and total_duration_sec and total_duration_sec > 0:
                feeder = ProgressFeeder(total_duration_sec, reporter)

            segments, info = model.transcribe(
                str(audio_path),
                language=language,
                vad_filter=False,
                word_timestamps=False,
            )

            def _ts(s: float) -> str:
                ms = int((s - int(s)) * 1000)
                s_int = int(s)
                h = s_int // 3600
                m = (s_int % 3600) // 60
                sec = s_int % 60
                return f"{h:02d}:{m:02d}:{sec:02d}.{ms:03d}"

            txt_lines: list[str] = []
            vtt_lines: list[str] = ["WEBVTT", ""]
            for seg in segments:
                if feeder is not None:
                    feeder.consume_line(f"[{_fmt_ts(seg.start)} --> {_fmt_ts(seg.end)}]")
                text = (getattr(seg, "text", "") or "").strip()
                if text:
                    txt_lines.append(text)
                    vtt_lines.append(f"{_fmt_ts(seg.start)} --> {_fmt_ts(seg.end)}")
                    vtt_lines.append(text)
                    vtt_lines.append("")

            if feeder is not None:
                feeder.done()

            vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")
            txt_path.write_text("\n".join(txt_lines), encoding="utf-8")

            with open(log_file, "a", encoding="utf-8", errors="ignore") as logf:
                dur = getattr(info, "duration", None)
                logf.write(f"faster-whisper: model={self.settings.model}, duration={dur}\n")

            return
        elif runner == "mlx":
            # Use mlx_whisper Python API (no CLI). Fail fast if not available.
            try:
                import mlx_whisper as _mlx  # type: ignore
            except Exception as exc:  # pragma: no cover - optional dep
                raise RuntimeError("mlx_whisper Python package is not installed in this environment.") from exc

            lang = _language_from_args(self.settings.extra_args)

            # Resolve the transcribe callable across known package layouts
            mlx_transcribe = None
            try:
                if hasattr(_mlx, "transcribe"):
                    mlx_transcribe = getattr(_mlx, "transcribe")
                else:  # e.g., module exposes function under submodule
                    from mlx_whisper.transcribe import transcribe as _t  # type: ignore
                    mlx_transcribe = _t
            except Exception:
                pass
            if mlx_transcribe is None:
                raise RuntimeError("mlx_whisper Python API not available: no transcribe() function found.")

            # Call with tolerant signature handling (some versions differ)
            result = None
            last_err: Exception | None = None
            for kwargs in (
                {"model": self.settings.model or "small.en", "language": lang},
                {"model": self.settings.model or "small.en"},
                {},
            ):
                try:
                    result = mlx_transcribe(str(audio_path), **kwargs)
                    break
                except TypeError as e:
                    last_err = e
                    continue
            if result is None:
                raise RuntimeError("mlx_whisper Python API call failed due to incompatible signature.") from last_err

            # Normalize segments from return value (dict/obj/list/generator)
            def _iter_segments(res):
                segs = None
                try:
                    segs = getattr(res, "segments")
                except Exception:
                    pass
                if segs is None and isinstance(res, dict):
                    segs = res.get("segments")
                if segs is None:
                    segs = res  # may already be an iterable of segments
                try:
                    for sg in segs or []:
                        yield sg
                except TypeError:
                    # Not iterable
                    return

            segments: list[tuple[float, float, str]] = []
            try:
                for seg in _iter_segments(result):
                    # Segment can be object or dict
                    s = 0.0
                    e = 0.0
                    t = ""
                    try:
                        s = float(getattr(seg, "start", seg.get("start", 0.0)))  # type: ignore[attr-defined]
                        e = float(getattr(seg, "end", seg.get("end", 0.0)))  # type: ignore[attr-defined]
                        raw_t = getattr(seg, "text", seg.get("text", ""))  # type: ignore[attr-defined]
                        t = (raw_t or "").strip()
                    except Exception:
                        continue
                    if t:
                        segments.append((s, e, t))
            except Exception as exc:
                raise RuntimeError("mlx_whisper Python API returned unexpected result shape.") from exc

            feeder: Optional[ProgressFeeder] = None
            if reporter is not None and total_duration_sec and total_duration_sec > 0:
                feeder = ProgressFeeder(total_duration_sec, reporter)

            txt_lines: list[str] = []
            vtt_lines: list[str] = ["WEBVTT", ""]
            for s, e, t in segments:
                if feeder is not None:
                    feeder.consume_line(f"[{_fmt_ts(s)} --> {_fmt_ts(e)}]")
                if t:
                    txt_lines.append(t)
                    vtt_lines.append(f"{_fmt_ts(s)} --> {_fmt_ts(e)}")
                    vtt_lines.append(t)
                    vtt_lines.append("")
            if feeder is not None:
                feeder.done()

            vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")
            txt_path.write_text("\n".join(txt_lines), encoding="utf-8")
            with open(log_file, "a", encoding="utf-8", errors="ignore") as logf:
                # Minimal diagnostics to help spot API differences
                ver = getattr(_mlx, "__version__", "unknown")
                logf.write(f"mlx-whisper: model={self.settings.model}, version={ver}, segments={len(segments)}\n")
            return
        else:  # "whisper" or "openai" Python package
            try:
                import whisper as ow  # type: ignore
            except Exception as exc:  # pragma: no cover - optional dep
                raise RuntimeError(
                    "The 'whisper' runner requires the 'openai-whisper' package. Install with 'pip install openai-whisper'."
                ) from exc

            model = ow.load_model(self.settings.model or "small.en")
            lang = _language_from_args(self.settings.extra_args)

            # Note: The Python API does not expose streaming progress callbacks.
            # We transcribe once and then emit a final progress update.
            result = model.transcribe(str(audio_path), language=lang, verbose=False)
            segs = result.get("segments") or []

            txt_lines: list[str] = []
            vtt_lines: list[str] = ["WEBVTT", ""]
            for seg in segs:
                s = float(seg.get("start", 0.0))
                e = float(seg.get("end", 0.0))
                t = (seg.get("text", "") or "").strip()
                if t:
                    txt_lines.append(t)
                    vtt_lines.append(f"{_fmt_ts(s)} --> {_fmt_ts(e)}")
                    vtt_lines.append(t)
                    vtt_lines.append("")

            vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")
            txt_path.write_text("\n".join(txt_lines), encoding="utf-8")

            # Emit final progress if reporter present
            if reporter is not None and total_duration_sec and total_duration_sec > 0:
                try:
                    reporter.on_update(100, int(total_duration_sec), int(total_duration_sec))
                except Exception:
                    pass
            with open(log_file, "a", encoding="utf-8", errors="ignore") as logf:
                logf.write(f"openai-whisper: model={self.settings.model}\n")
            return


def get_runner(settings: WhisperSettings) -> WhisperRunner:
    # Single public class for tests; internally branches on runner setting.
    return WhisperRunner(settings)
