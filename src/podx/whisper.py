from __future__ import annotations

import subprocess
from pathlib import Path
from .config import WhisperSettings


class WhisperRunner:
    def __init__(self, settings: WhisperSettings):
        self.settings = settings

    def transcribe(self, audio_path: Path, vtt_path: Path, txt_path: Path, log_file: Path) -> None:
        """Run whisper to produce VTT and TXT transcripts."""
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

        with open(log_file, "a") as logf:
            subprocess.run(cmd, check=True, stdout=logf, stderr=subprocess.STDOUT)


def get_runner(settings: WhisperSettings) -> WhisperRunner:
    # only mlx runner implemented for now
    return WhisperRunner(settings)
