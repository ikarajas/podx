from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from . import __version__


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
        from .services import IngestionService
        from .progress import ConsoleProgressReporter

        service = IngestionService()
        try:
            result = service.ingest_episode(
                Path(args.audio), args.podcast, args.episode, args.force, ConsoleProgressReporter()
            )
            if result is None:
                print("Transcript already exists, nothing to do.")
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

        service = DirectoryService()
        podcasts = service.search_podcasts(args.name)
        for p in podcasts:
            print(f"Podcast Name: {p.name}")
            print(f"Feed URL: {p.feed_url}")
            print(f"Genres: {', '.join(p.genres)}")
            print()
        return 0

    search_p.set_defaults(func=_search)

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

