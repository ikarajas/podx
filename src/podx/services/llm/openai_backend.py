from __future__ import annotations

import os
from typing import Optional

from .base import SummarizationBackend

_DEFAULT_MODEL = "gpt-4o-mini"
_MAX_TOKENS = 1024


class OpenAIBackend(SummarizationBackend):
    """Summarisation backend using OpenAI.

    Requires ``openai`` (``pip install -e .[openai]``).
    API key from ``OPENAI_API_KEY`` environment variable.
    """

    def __init__(self, *, model: Optional[str] = None, timeout: int = 60) -> None:
        try:
            import openai  # type: ignore
        except ImportError:
            raise ImportError(
                "openai is required for the OpenAI provider. "
                "Install it with: pip install -e .[openai]"
            )
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is not set."
            )
        self._client = openai.OpenAI(api_key=api_key, timeout=float(timeout))
        self._model_name = model or _DEFAULT_MODEL

    def summarize(self, text: str, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model_name,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""


__all__ = ["OpenAIBackend"]
