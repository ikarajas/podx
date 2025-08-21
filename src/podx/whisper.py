from __future__ import annotations

import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

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
        """Run whisper to produce VTT and TXT transcripts.

        Streams stdout line-by-line, tees to the provided log file, and optionally
        feeds lines to a progress parser via ``reporter`` + ``total_duration_sec``.
        """
        # mlx_whisper can emit multiple formats in a single run by specifying
        # an output directory/name and using ``--output-format all``.  The
        # caller provides the desired VTT and TXT paths which share the same
        # directory and stem; derive those values to pass to the CLI.
        output_dir = vtt_path.parent
        output_name = vtt_path.stem

        cmd = [
            "mlx_whisper",
            str(audio_path),
            "--model",
            self.settings.model,
            "--output-dir",
            str(output_dir),
            "--output-name",
            output_name,
            "--output-format",
            "all",
        ]
        cmd.extend(self.settings.extra_args)

        feeder: Optional[ProgressFeeder] = None
        if reporter is not None and total_duration_sec and total_duration_sec > 0:
            feeder = ProgressFeeder(total_duration_sec, reporter)

        # Use Popen to stream output line-by-line and tee to log
        with open(log_file, "a", encoding="utf-8", errors="ignore") as logf:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )
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


def get_runner(settings: WhisperSettings) -> WhisperRunner:
    # only mlx runner implemented for now
    return WhisperRunner(settings)
