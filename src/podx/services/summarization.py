"""Podcast episode summarisation service.

Uses a pluggable LLM backend (Gemini, Anthropic, OpenAI, or Ollama) to produce
a concise summary from a transcript text file.  Results are cached to disk so
re-opening an episode does not trigger a new API call.

Provider selection and model are controlled via ``Config.llm``; see
``services/config.py`` for the full set of options.  API keys must be supplied
via environment variables — they are never written to disk.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .config import Config
from .episodes_index import EpisodesIndexService
from .llm.base import SummarizationBackend


class SummarizationService:
    """Summarise podcast transcripts via a configured LLM backend.

    Inject into :class:`~podx.services.jobs.JobsService` to enable background
    summarisation jobs, or call :meth:`summarize_episode` directly from the CLI.
    """

    def __init__(self, cfg: Config, episodes_index: EpisodesIndexService) -> None:
        self._cfg = cfg
        self._episodes_index = episodes_index

    def get_backend(self) -> SummarizationBackend:
        """Instantiate the configured backend.

        Raises :exc:`ImportError` if the required package is not installed, or
        :exc:`RuntimeError` if a required API key is missing.
        """
        provider = self._cfg.llm.provider
        model = self._cfg.llm.model
        timeout = self._cfg.llm.timeout_sec
        if provider == "gemini":
            from .llm.gemini import GeminiBackend
            return GeminiBackend(model=model, timeout=timeout)
        if provider == "anthropic":
            from .llm.anthropic_backend import AnthropicBackend
            return AnthropicBackend(model=model, timeout=timeout)
        if provider == "openai":
            from .llm.openai_backend import OpenAIBackend
            return OpenAIBackend(model=model, timeout=timeout)
        if provider == "ollama":
            from .llm.ollama import OllamaBackend
            return OllamaBackend(
                host=self._cfg.llm.ollama_host,
                model=self._cfg.llm.ollama_model or model or "llama3",
                timeout=timeout,
            )
        raise ValueError(f"Unknown LLM provider: {provider!r}")

    def build_prompt(self, text: str) -> str:
        wc = self._cfg.summarization.word_count
        return (
            f"You are summarising a podcast episode transcript. "
            f"Write a concise summary of approximately {wc} words covering "
            f"the key topics and main takeaways. Be clear and informative.\n\n"
            f"Transcript:\n{text}"
        )

    def summarize_episode(
        self,
        txt_path: Path,
        episode_dir: Path,
        *,
        key: str,
        title: str,
        published_date: Optional[str],
        guid: Optional[str],
        enclosure_url: Optional[str],
        force: bool = False,
    ) -> Path:
        """Summarise a transcript and cache the result to disk.

        Writes the summary to ``{episode_dir}/summary.txt`` and updates the
        episode index.  If the file already exists and ``force`` is ``False``,
        the cached version is returned immediately without calling the LLM.

        Returns the path to the summary file.
        Raises on LLM errors (network failures, bad API keys, rate limits).
        """
        summary_path = episode_dir / "summary.txt"
        if summary_path.exists() and not force:
            return summary_path
        text = txt_path.read_text(encoding="utf-8", errors="ignore")
        prompt = self.build_prompt(text)
        backend = self.get_backend()
        summary = backend.summarize(text, prompt)
        episode_dir.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(summary, encoding="utf-8")
        self._episodes_index.mark_summary(
            key,
            title=title,
            published_date=published_date,
            guid=guid,
            enclosure_url=enclosure_url,
            summary_path=summary_path,
            episode_dir=episode_dir,
        )
        return summary_path


__all__ = ["SummarizationService"]
