from __future__ import annotations

import subprocess
from pathlib import Path
from .config import WhisperSettings


class WhisperRunner:
    def __init__(self, settings: WhisperSettings):
        self.settings = settings

    def transcribe(self, audio_path: Path, vtt_path: Path, txt_path: Path, log_file: Path) -> None:
        """Run whisper to produce VTT and TXT transcripts."""
        cmd_base = ["mlx_whisper", str(audio_path), "--model", self.settings.model]
        cmd_base.extend(self.settings.extra_args)
        # VTT
        cmd_vtt = cmd_base + ["--output_format", "vtt", "--output", str(vtt_path)]
        with open(log_file, "a") as logf:
            subprocess.run(cmd_vtt, check=True, stdout=logf, stderr=subprocess.STDOUT)
        # TXT
        cmd_txt = cmd_base + ["--output_format", "txt", "--output", str(txt_path)]
        with open(log_file, "a") as logf:
            subprocess.run(cmd_txt, check=True, stdout=logf, stderr=subprocess.STDOUT)


def get_runner(settings: WhisperSettings) -> WhisperRunner:
    # only mlx runner implemented for now
    return WhisperRunner(settings)
