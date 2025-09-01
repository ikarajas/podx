from __future__ import annotations

import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional
import os

import sys
import shutil
from podx.services.config import WhisperSettings
from podx.services.progress import ProgressFeeder, ProgressReporter


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
        """Run Whisper to produce VTT and TXT transcripts.

        The underlying engine is selected via ``settings.runner``:
        - "mlx": uses the ``mlx_whisper`` CLI (macOS arm64)
        - "whisper"/"openai": uses the ``whisper`` CLI (cross-platform)

        Streams stdout line-by-line, tees to ``log_file``, and optionally feeds
        lines to a progress parser via ``reporter`` + ``total_duration_sec``.
        """
        runner = (self.settings.runner or "").lower()

        # For the OpenAI whisper CLI, ffmpeg is required. For MLX, many inputs
        # still rely on ffmpeg for decoding, but we don't hard-require it to
        # allow simple WAV cases to proceed.

        # All runners write to tmp output directory; ensure exists
        output_dir = vtt_path.parent
        output_stem = vtt_path.stem

        # Build command per engine
        if runner == "mlx":
            cmd = [
                "mlx_whisper",
                str(audio_path),
                "--model",
                self.settings.model,
                "--output-dir",
                str(output_dir),
                "--output-name",
                output_stem,
                "--output-format",
                "all",
            ]
        elif runner == "faster":
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
                    feeder.consume_line(f"[{_ts(seg.start)} --> {_ts(seg.end)}]")
                text = (getattr(seg, "text", "") or "").strip()
                if text:
                    txt_lines.append(text)
                    vtt_lines.append(f"{_ts(seg.start)} --> {_ts(seg.end)}")
                    vtt_lines.append(text)
                    vtt_lines.append("")

            if feeder is not None:
                feeder.done()

            output_dir.mkdir(parents=True, exist_ok=True)
            vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")
            txt_path.write_text("\n".join(txt_lines), encoding="utf-8")

            with open(log_file, "a", encoding="utf-8", errors="ignore") as logf:
                dur = getattr(info, "duration", None)
                logf.write(f"faster-whisper: model={self.settings.model}, duration={dur}\n")

            return
        else:
            if shutil.which("ffmpeg") is None:
                raise RuntimeError(
                    "ffmpeg is required for the 'whisper' runner but not found on PATH. Install ffmpeg and try again."
                )
            # Default to OpenAI Whisper CLI for non-MLX platforms
            # Note: OpenAI whisper uses output_dir only; filenames are based on input stem.
            cmd = [
                "whisper",
                str(audio_path),
                "--model",
                self.settings.model or "small.en",
                "--output_dir",
                str(output_dir),
                "--output_format",
                "all",
            ]

        cmd.extend(self.settings.extra_args)

        feeder: Optional[ProgressFeeder] = None
        if reporter is not None and total_duration_sec and total_duration_sec > 0:
            feeder = ProgressFeeder(total_duration_sec, reporter)

        # Use Popen to stream output line-by-line and tee to log
        with open(log_file, "a", encoding="utf-8", errors="ignore") as logf:
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                )
            except FileNotFoundError as exc:
                engine = "mlx_whisper" if runner == "mlx" else "whisper"
                raise RuntimeError(
                    f"'{engine}' is not available on this system. Install the appropriate package and ensure ffmpeg is installed."
                ) from exc

            assert proc.stdout is not None
            for line in proc.stdout:
                logf.write(line)
                if feeder is not None:
                    feeder.consume_line(line)
            rc = proc.wait()
            if feeder is not None:
                feeder.done()
            if rc != 0:
                raise subprocess.CalledProcessError(rc, cmd)

        # The mlx runner already wrote to the exact desired filenames via output-name.
        # For the whisper CLI fallback, rename outputs to the expected paths.
        if runner != "mlx":
            src_vtt = output_dir / f"{audio_path.stem}.vtt"
            src_txt = output_dir / f"{audio_path.stem}.txt"
            if src_vtt.exists() and src_vtt != vtt_path:
                # Overwrite if present from a previous attempt
                if vtt_path.exists():
                    vtt_path.unlink()
                shutil.move(str(src_vtt), str(vtt_path))
            if src_txt.exists() and src_txt != txt_path:
                if txt_path.exists():
                    txt_path.unlink()
                shutil.move(str(src_txt), str(txt_path))


def get_runner(settings: WhisperSettings) -> WhisperRunner:
    # Single public class for tests; internally branches on runner setting.
    return WhisperRunner(settings)
