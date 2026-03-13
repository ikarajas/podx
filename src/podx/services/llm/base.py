from __future__ import annotations

from abc import ABC, abstractmethod


class SummarizationBackend(ABC):
    @abstractmethod
    def summarize(self, text: str, prompt: str) -> str:
        """Call the LLM and return the summary string. Raises on error."""


__all__ = ["SummarizationBackend"]
