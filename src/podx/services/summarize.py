from __future__ import annotations

"""Summarization services.

This module provides a chunked map-reduce summarization flow that targets
ChatGPT (OpenAI) by default while keeping the model configurable.

Notes
- Services avoid printing; callers may use a suitable ProgressReporter.
- Chunking uses character-based limits to work without tokenizer deps.
"""

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence
import os

from .config import Config


# ---- Public spec -----------------------------------------------------------------


@dataclass
class SummarizeSpec:
    style: str = "bullets"  # bullets | abstract | chapters | notes
    language: str = "en"
    model: Optional[str] = None
    max_output_tokens: Optional[int] = None
    # Advanced (mostly internal):
    chunk_chars: Optional[int] = None
    overlap_chars: Optional[int] = None
    strategy: Optional[str] = None  # map_reduce | refine | single


class SummarizationError(RuntimeError):
    pass


# ---- Core service ----------------------------------------------------------------


class SummarizationService:
    """High-level orchestrator for transcript summarization.

    - Splits text into chunks with overlap on sentence/paragraph boundaries
    - Runs a map step (per-chunk summaries)
    - Runs a reduce step (synthesize final summary)
    """

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    # Public API
    def summarize_text(self, text: str, spec: SummarizeSpec) -> str:
        if not text or not text.strip():
            raise SummarizationError("Empty input text for summarization")

        # Resolve effective parameters from config/spec
        style = (spec.style or self.cfg.summarization.default_style).lower()
        model = spec.model or self.cfg.llm.model
        max_output_tokens = spec.max_output_tokens or self.cfg.llm.max_output_tokens
        strategy = (spec.strategy or self.cfg.summarization.strategy).lower()
        chunk_chars = int(spec.chunk_chars or self.cfg.summarization.chunk_chars)
        overlap_chars = int(spec.overlap_chars or self.cfg.summarization.overlap_chars)

        if strategy == "single":
            prompt = _final_prompt(style, spec.language)
            return _call_openai(model, [
                {"role": "system", "content": _system_instructions()},
                {"role": "user", "content": prompt + "\n\n" + text},
            ], max_output_tokens=max_output_tokens)

        # Chunk text and map-reduce
        chunks = list(_chunk_text(text, chunk_chars, overlap_chars))
        if not chunks:
            chunks = [text]

        # Map step
        map_prompt = _map_prompt(style, spec.language)
        partials: list[str] = []
        for ch in chunks:
            out = _call_openai(model, [
                {"role": "system", "content": _system_instructions()},
                {"role": "user", "content": map_prompt + "\n\n" + ch},
            ], max_output_tokens=max_output_tokens)
            partials.append(out.strip())

        # Reduce step
        reduce_prompt = _reduce_prompt(style, spec.language)
        joined = "\n\n".join(f"[Chunk {i+1}]\n{p}" for i, p in enumerate(partials))
        final = _call_openai(model, [
            {"role": "system", "content": _system_instructions()},
            {"role": "user", "content": reduce_prompt + "\n\n" + joined},
        ], max_output_tokens=max_output_tokens)
        return final.strip()


# ---- Prompt templates -------------------------------------------------------------


def _system_instructions() -> str:
    return (
        "You are a careful assistant that writes accurate, concise summaries. "
        "Only use information present in the provided transcript text. If a detail is missing, say 'insufficient context'."
    )


def _map_prompt(style: str, language: str) -> str:
    if style == "abstract":
        return (
            f"Summarize the following transcript chunk into a short abstract in {language}. "
            "Capture the main themes and conclusions. Avoid speculation."
        )
    if style == "chapters":
        return (
            f"From the following transcript chunk, extract time-coded chapter candidates in {language}. "
            "Format as '- [mm:ss] Title — 1 line description'. Use times if present; otherwise omit timestamps."
        )
    if style == "notes":
        return (
            f"Create concise show notes in {language} from the following transcript chunk. "
            "Include key topics, people, and resources mentioned."
        )
    # default bullets
    return (
        f"Summarize the following transcript chunk in {language} as 5-10 crisp bullet points. "
        "Use factual, neutral phrasing and avoid repetition."
    )


def _reduce_prompt(style: str, language: str) -> str:
    if style == "abstract":
        return (
            f"Combine the chunk summaries into a single coherent abstract in {language}. "
            "Prefer coverage and accuracy over style. 180-300 words."
        )
    if style == "chapters":
        return (
            f"Merge and deduplicate the chapter candidates below into a clean list in {language}. "
            "Prefer consistent timestamps and ordering. 8-15 items."
        )
    if style == "notes":
        return (
            f"Merge the chunk notes into a single set of show notes in {language}, "
            "grouping by topic and removing duplicates."
        )
    # default bullets
    return (
        f"Synthesize a final list of key takeaways in {language} from the chunk summaries below. "
        "Return 8-15 bullets, de-duplicated and comprehensive."
    )


def _final_prompt(style: str, language: str) -> str:
    # Used for single-pass summarization
    if style == "abstract":
        return f"Summarize the transcript into a short abstract in {language}. 180-300 words."
    if style == "chapters":
        return f"Produce time-coded chapter titles in {language}. Format '- [mm:ss] Title — 1 line'."
    if style == "notes":
        return f"Write concise show notes in {language} with topics, people, and resources."
    return f"Summarize the transcript as 8-15 concise bullet points in {language}."


# ---- Chunking --------------------------------------------------------------------


def _split_paragraphs(text: str) -> list[str]:
    # Split on double newlines; keep simple to avoid heavy deps
    blocks = [b.strip() for b in text.replace("\r\n", "\n").split("\n\n")]
    return [b for b in blocks if b]


def _chunk_text(text: str, chunk_chars: int, overlap_chars: int) -> Iterable[str]:
    """Yield chunks with soft boundaries and small overlaps.

    The policy is paragraph-first packing with an overlap (context carry-over).
    """
    chunk_chars = max(2000, int(chunk_chars))  # guardrails
    overlap_chars = max(0, int(overlap_chars))
    paras = _split_paragraphs(text)
    if not paras:
        yield text[:chunk_chars]
        text_rest = text[chunk_chars:]
        i = 0
        while text_rest:
            i += 1
            prefix = text[(i * chunk_chars - min(overlap_chars, chunk_chars)) : i * chunk_chars]
            yield prefix + text_rest[:chunk_chars]
            text_rest = text_rest[chunk_chars:]
        return

    cur: list[str] = []
    cur_len = 0
    for p in paras:
        if cur_len + len(p) + (2 if cur else 0) <= chunk_chars:
            cur.append(p)
            cur_len += len(p) + (2 if cur_len > 0 else 0)
            continue
        if cur:
            chunk = "\n\n".join(cur).strip()
            yield chunk
            # Prepare overlap: take tail of current chunk
            if overlap_chars > 0:
                tail = chunk[-overlap_chars:]
                cur = [tail, p]
                cur_len = len(tail) + len(p)
            else:
                cur = [p]
                cur_len = len(p)
        else:
            # Single paragraph longer than chunk; hard-split
            start = 0
            while start < len(p):
                end = min(len(p), start + chunk_chars)
                yield p[start:end]
                if end >= len(p):
                    break
                if overlap_chars > 0:
                    start = end - overlap_chars
                else:
                    start = end
            cur = []
            cur_len = 0
    if cur:
        yield "\n\n".join(cur).strip()


# ---- Provider (OpenAI) -----------------------------------------------------------


def _call_openai(model: str, messages: Sequence[dict], *, max_output_tokens: Optional[int]) -> str:
    """Call OpenAI Chat Completions API.

    This function defers the import so the package remains optional, and reads
    the API key from the standard OPENAI_API_KEY environment variable.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SummarizationError(
            "OPENAI_API_KEY is not set. Set it in your environment to enable summarization."
        )

    # Try modern SDK first, fall back to legacy
    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=list(messages),
            temperature=0.2,
            max_tokens=max_output_tokens,
        )
        content = resp.choices[0].message.content or ""
        return content
    except ModuleNotFoundError:
        pass
    except Exception as exc:  # pragma: no cover - defensive around SDK changes
        raise SummarizationError(f"OpenAI SDK error: {exc}") from exc

    # Legacy SDK path
    try:
        import openai  # type: ignore

        openai.api_key = api_key
        resp = openai.ChatCompletion.create(
            model=model,
            messages=list(messages),
            temperature=0.2,
            max_tokens=max_output_tokens,
        )
        content = resp["choices"][0]["message"]["content"]
        return str(content or "")
    except ModuleNotFoundError as exc:
        raise SummarizationError(
            "The 'openai' package is not installed. Install it to use summarization (e.g., 'pip install openai')."
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive around SDK changes
        raise SummarizationError(f"OpenAI API error: {exc}") from exc


__all__ = ["SummarizationService", "SummarizeSpec", "SummarizationError"]

