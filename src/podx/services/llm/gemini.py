from __future__ import annotations

import os
from typing import Optional

from .base import SummarizationBackend

_DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiBackend(SummarizationBackend):
    """Summarisation backend using Google Gemini.

    Requires ``google-generativeai`` (``pip install -e .[gemini]``).
    API key from ``GEMINI_API_KEY`` or ``GOOGLE_API_KEY`` environment variable.
    """

    def __init__(self, *, model: Optional[str] = None, timeout: int = 60) -> None:
        try:
            import google.generativeai as genai  # type: ignore
        except ImportError:
            raise ImportError(
                "google-generativeai is required for the Gemini provider. "
                "Install it with: pip install -e .[gemini]"
            )
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY (or GOOGLE_API_KEY) environment variable is not set."
            )
        genai.configure(api_key=api_key)
        self._model_name = model or _DEFAULT_MODEL
        self._timeout = timeout
        self._genai = genai

    def summarize(self, text: str, prompt: str) -> str:
        model = self._genai.GenerativeModel(self._model_name)
        response = model.generate_content(
            prompt,
            request_options={"timeout": self._timeout},
        )
        return response.text


__all__ = ["GeminiBackend"]
