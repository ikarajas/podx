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

## PyQt6 Import Notes (UI tests and dev env)

- The repo contains a lightweight compatibility stub at `src/PyQt6/__init__.py` so
  optional Qt usage can fail fast with a clear ImportError when the native Qt
  libraries aren’t present. The stub defers to the real PyPI wheel (`PyQt6`) and
  validates that `PyQt6.QtCore` can be imported.
- To avoid the local stub shadowing the real wheel during tests, import PyQt6
  before adding the project `src/` path to `sys.path` (the UI tests already do
  this). Alternatively, ensure your test run uses the virtualenv interpreter
  where `PyQt6` is installed and that `site-packages` precedes the project’s
  `src` on `PYTHONPATH`.
- Headless Qt: UI tests run with `QT_QPA_PLATFORM=offscreen`. Keep this env var
  set in CI and local test runs to avoid requiring a display server.
- Always run UI tests: PyQt6 is a declared dependency in `pyproject.toml`. The
  UI tests do not auto-skip; if `PyQt6.QtCore` cannot be imported (e.g., wrong
  interpreter), the test collection fails, making the issue explicit.
- Common failure: `ImportError: No module named 'PyQt6.QtCore'`. Fix by:
  - Running tests with the venv’s Python: `python -m pytest -q` where `python`
    is `.venv/bin/python`.
  - Verifying PyQt6 and its bundled Qt are installed: `pip show PyQt6 PyQt6-Qt6`.
  - Ensuring the local stub isn’t taking precedence (see import-order note).

Tip: If your workflow prefers keeping UI tests optional, add a `@pytest.mark.ui`
marker and run them in a dedicated job; otherwise, keep the current “always run”
setup for stronger regression coverage.

## Qt Threading Guidelines

- Services may invoke callbacks from worker threads. Qt widgets must only be
  touched on the GUI thread.
- In views, marshal background updates with signals or `QMetaObject.invokeMethod`
  using `Qt.QueuedConnection`; `QTimer.singleShot` without a QObject target is
  unreliable. See `docs/ui-threading.md` for examples.

## Documentation Strategy

Keep high-level guidance in the top-level README and deeper, evolving details in docs/*. The goal is to make it easy to understand where new code belongs, how to extend features, and why notable choices were made.

Recommended layout
- README: Quick start, CLI/GUI usage, configuration, and a short Architecture Overview with links to deeper docs.
- AGENTS.md (this file): Architecture, layering rules, contribution guidelines, and engineering practices (testing, performance patterns, config/progress injection).
- docs/: Feature- and subsystem-specific documents. Examples:
  - docs/feeds-metadata.md — subscription keys, cache layout, TTL/retention policy.
  - docs/ui-performance.md — item view performance checklist (uniform sizes, batching, async thumbnails, caching).
  - docs/ingestion-pipeline.md — ingestion steps, file layout, error handling and locking.
- Architecture Decision Records (ADRs) — optional but encouraged for notable decisions: short records under `docs/adr/NNN-title.md` for choices that affect future work (e.g., key format `slug--shortid`, retention policy defaults, paging strategy). Keep them concise and link them from relevant docs.

When to document
- Any change that affects public behavior, storage formats, paths, or cross-cutting architecture (e.g., how services interact) must update or add docs alongside code.
- UI/UX-affecting changes should note user-visible behavior and config knobs.
- Performance-impacting patterns (e.g., model batching, async fetch) belong in docs/ui-performance.md.

PR checklist (treat as a mental checklist)
- Code follows layering rules (services hold logic; UI stays thin; no prints in services).
- Config is injected (avoid global reads in services).
- Progress for long operations uses ProgressReporter.
- Tests added/updated when behavior changes.
- Docs updated:
  - README cross-links if new subsystems are introduced.
  - Feature docs in docs/… are added/updated.
  - ADR added for decisions that will steer future changes.

Architecture Decision Records (ADRs): suggested template
- Title: Decision summary
- Context: What problem are we solving?
- Decision: The choice made and key rationale.
- Consequences: Pros/cons, risks, and how this impacts future work.
- Alternatives considered: Briefly, with why they weren’t chosen.

Cross-linking and ownership
- From code comments or error messages, include pointers to relevant docs when it helps discovery.
- Services should link to their corresponding docs section at the top of the module when non-obvious (keep brief; avoid redundancy).

## Feed Metadata and Subscription Keys

- UI reads cached channel metadata via `podx.services.feeds_meta.FeedsMetaService`.
- Keys are human‑readable (`slug--shortid`) and stable per subscription; services
  that write per‑podcast data should use `FeedsMetaService.podcast_dir(name, feed_url)`
  instead of hand‑rolled paths.
- Network access and parsing (e.g., conditional RSS fetch) lives in services
  (`RssService`), not in UI code. The UI may trigger background refreshes but
  should avoid blocking the event loop.
