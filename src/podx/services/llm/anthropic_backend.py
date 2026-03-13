from __future__ import annotations

import os
from typing import Optional

from .base import SummarizationBackend

_DEFAULT_MODEL = "claude-3-5-haiku-20241022"
_MAX_TOKENS = 1024


class AnthropicBackend(SummarizationBackend):
    """Summarisation backend using Anthropic Claude.

    Requires ``anthropic`` (``pip install -e .[anthropic]``).
    API key from ``ANTHROPIC_API_KEY`` environment variable.
    """

    def __init__(self, *, model: Optional[str] = None, timeout: int = 60) -> None:
        try:
            import anthropic  # type: ignore
        except ImportError:
            raise ImportError(
                "anthropic is required for the Anthropic provider. "
                "Install it with: pip install -e .[anthropic]"
            )
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY environment variable is not set."
            )
        self._client = anthropic.Anthropic(api_key=api_key, timeout=float(timeout))
        self._model_name = model or _DEFAULT_MODEL

    def summarize(self, text: str, prompt: str) -> str:
        message = self._client.messages.create(
            model=self._model_name,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text


__all__ = ["AnthropicBackend"]
