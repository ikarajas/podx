# AGENTS

## Architecture Overview
- **Core services** under `src/podx/services/` contain the domain logic and shared
  infrastructure.
  - `Config` dataclasses and `load_config` live in `podx.services.config`.
  - Progress reporting strategies are defined in `podx.services.progress`
    (`ProgressReporter`, `ConsoleProgressReporter`, `QtProgressReporter`).
  - `WhisperRunner` provides transcription helpers in `podx.services.whisper`.
  - `IngestionService` transcribes audio and writes episode metadata.
  - `DirectoryService` searches podcast directories.
- The **CLI layer** in `src/podx/cli.py` is a thin interface that delegates to
  services.
- Runtime configuration is loaded from `~/.podx/config.yaml` (or `PODX_CONFIG`)
  via `get_config()`.

## Rationale
Keeping services free of presentation concerns makes it possible to reuse them
in other front‑ends. A future Qt application can plug in its own
`ProgressReporter` and UI without reworking the underlying logic.

## Contribution Guidelines
- Place new business logic in services; keep the CLI focused on argument parsing
  and user interaction.
- Avoid calling `print` in services. Return data or use a `ProgressReporter` to
  surface progress.
- Inject a `Config` object into services or functions instead of reading global
  state directly.
- Use `ProgressReporter` for long‑running operations.
- Include tests for new functionality and ensure `pytest` passes before
  committing.
- Import configuration, progress reporting, and Whisper helpers from the
  `podx.services` namespace; legacy top-level modules have been removed.
