from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from podx.services.progress import ConsoleProgressReporter

from . import __version__
from .app import get_config
from .services import IngestionService, SummarizationService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="podx",
        description="podx – a minimal command-line tool scaffold",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the version and exit.",
    )

    subparsers = parser.add_subparsers(dest="command")

    ingest_p = subparsers.add_parser("ingest", help="Ingest an episode for transcription")
    ingest_p.add_argument("--podcast", help="Podcast name", default=None)
    ingest_p.add_argument("--episode", help="Episode title", default=None)
    ingest_p.add_argument("--audio", required=True, help="Path to audio file")
    ingest_p.add_argument("--force", action="store_true", help="Overwrite existing transcript")

    def _ingest(args: argparse.Namespace) -> int:
        service = IngestionService(get_config())
        try:
            result = service.ingest_episode(
                Path(args.audio), args.podcast, args.episode, args.force, ConsoleProgressReporter()
            )
            if result is None:
                print("Transcript already exists, nothing to do.")
            else:
                print(
                    f"Ingested '{result.episode_title}' from '{result.podcast}'"
                )
                print(f"Transcript saved to: {result.transcript.txt_path}")
            return 0
        except FileNotFoundError:
            print("Audio file not found")
            return 1
        except Exception as exc:
            print(str(exc))
            return 1

    ingest_p.set_defaults(func=_ingest)

    search_p = subparsers.add_parser("search", help="Search for podcasts")
    search_p.add_argument("name", help="Podcast name to search for")

    def _search(args: argparse.Namespace) -> int:
        from .services import DirectoryService

        service = DirectoryService(get_config())
        podcasts = service.search_podcasts(args.name)
        for p in podcasts:
            print(f"Podcast Name: {p.name}")
            print(f"Feed URL: {p.feed_url}")
            print(f"Genres: {', '.join(p.genres)}")
            print()
        return 0

    search_p.set_defaults(func=_search)

    ui_p = subparsers.add_parser("ui", help="Launch the graphical user interface")

    def _ui(_args: argparse.Namespace) -> int:
        try:
            from .ui.main import main as ui_main
        except ModuleNotFoundError as exc:  # pragma: no cover - import error message
            print(str(exc))
            return 1
        return ui_main()

    ui_p.set_defaults(func=_ui)

    # summarize: Summarize a transcript via ChatGPT
    sum_p = subparsers.add_parser("summarize", help="Summarize a transcript using ChatGPT (model configurable)")
    sum_p.add_argument("--file", "-f", help="Path to transcript text file ('-' for stdin)", required=True)
    sum_p.add_argument("--out", "-o", help="Write summary to this file (default: stdout)")
    sum_p.add_argument("--style", choices=["bullets", "abstract", "chapters", "notes"], default=None, help="Summary style")
    sum_p.add_argument("--language", "-l", default="en", help="Output language (e.g., en, es)")
    sum_p.add_argument("--model", "-m", default=None, help="Override model (default from config)")
    sum_p.add_argument("--single", action="store_true", help="Force single-pass summarization (no chunking)")
    sum_p.add_argument("--chunk-chars", type=int, default=None, help="Approx chars per chunk (override config)")
    sum_p.add_argument("--overlap-chars", type=int, default=None, help="Chars of overlap between chunks")
    sum_p.add_argument("--max-output-tokens", type=int, default=None, help="Max tokens for each response")

    def _summarize(args: argparse.Namespace) -> int:
        cfg = get_config()
        service = SummarizationService(cfg)

        # Read input
        if args.file == "-":
            import sys
            data = sys.stdin.read()
            src_desc = "stdin"
        else:
            p = Path(args.file).expanduser().resolve()
            if not p.exists():
                print("Transcript file not found")
                return 1
            data = p.read_text(encoding="utf-8", errors="ignore")
            src_desc = str(p)

        from podx.services.summarize import SummarizeSpec, SummarizationError

        spec = SummarizeSpec(
            style=args.style or cfg.summarization.default_style,
            language=args.language,
            model=args.model or cfg.llm.model,
            max_output_tokens=args.max_output_tokens or cfg.llm.max_output_tokens,
            chunk_chars=args.chunk_chars or cfg.summarization.chunk_chars,
            overlap_chars=args.overlap_chars or cfg.summarization.overlap_chars,
            strategy="single" if args.single else cfg.summarization.strategy,
        )

        try:
            print(f"Summarizing ({spec.style}) from {src_desc} using model '{spec.model}'…")
            summary = service.summarize_text(data, spec)
        except SummarizationError as exc:
            print(str(exc))
            return 1
        except Exception as exc:
            print(f"Summarization failed: {exc}")
            return 1

        if args.out:
            out_path = Path(args.out).expanduser().resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(summary)
            print(f"Summary written to: {out_path}")
        else:
            print(summary)
        return 0

    sum_p.set_defaults(func=_summarize)

    # Default action: show help when no subcommands/args are provided
    parser.set_defaults(func=lambda _args: parser.print_help())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = args.func(args) if hasattr(args, "func") else None
    return int(result) if isinstance(result, int) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

