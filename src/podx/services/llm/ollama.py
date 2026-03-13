from __future__ import annotations

import json
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from .base import SummarizationBackend

_DEFAULT_HOST = "http://localhost:11434"
_DEFAULT_MODEL = "llama3"


class OllamaBackend(SummarizationBackend):
    """Summarisation backend using a local Ollama instance.

    No extra package required — uses urllib from the standard library.
    Configure host and model in config.yaml under ``llm.ollama_host`` and
    ``llm.ollama_model``, or pass them directly.
    """

    def __init__(
        self,
        *,
        host: str = _DEFAULT_HOST,
        model: Optional[str] = None,
        timeout: int = 60,
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model or _DEFAULT_MODEL
        self._timeout = timeout

    def summarize(self, text: str, prompt: str) -> str:
        url = f"{self._host}/api/generate"
        payload = json.dumps({
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }).encode("utf-8")
        req = Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=self._timeout) as resp:
                body = resp.read().decode("utf-8")
        except URLError as e:
            raise RuntimeError(
                f"Could not connect to Ollama at {self._host}: {e}. "
                "Ensure Ollama is running (https://ollama.com)."
            ) from e
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            raise RuntimeError(f"Unexpected response from Ollama: {body[:200]}")
        if "error" in data:
            raise RuntimeError(f"Ollama error: {data['error']}")
        return data.get("response", "")


__all__ = ["OllamaBackend"]
