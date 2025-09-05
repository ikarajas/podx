# Ingestion Pipeline

This document outlines how Podx ingests an episode: from source audio to
persisted transcripts and status updates.

## Steps

- Detect metadata: `duration_sec`, podcast title, episode title, date (via
  Mutagen when available).
- Determine target directories using `FeedsMetaService.podcast_dir(name, url)`
  when a subscription context (feed URL) is known.
- Acquire an episode lock (`.lock`) to prevent concurrent work on the same
  episode.
- Set up `tmp/` and `logs/` inside the episode directory.
- Copy source audio to `tmp/` and invoke a runner via `WhisperRunner`:
  - `mlx` (default on macOS arm64)
  - `whisper` (OpenAI Whisper Python package) on other platforms
  - `faster` (Faster‑Whisper) when enabled
- Write `transcript.vtt` and `transcript.txt` to `tmp/`, then atomically move
  them into the episode directory and remove `tmp/`.
- Write `episode.json` with metadata, and update the per‑subscription
  `episodes_index.json` entry.

## Progress Reporting

- Services emit progress via `ProgressReporter`. The UI should not block; it
  only updates state.
- Streaming progress depends on the runner:
  - `mlx`: some versions return all segments at the end; streaming can be
    limited. A future improvement (below) describes robust progress via a child
    process.
  - `whisper`: no streaming callbacks (expect 0% → 100%).
  - `faster`: streams segments incrementally; a `ProgressFeeder` converts
    timestamps to percentage when duration is known.

## Future: Child‑Process Transcription (Design Note)

Goal: Make progress updates reliable for runners that don’t yield frequently
within the Python process (notably `mlx` on macOS), while improving
responsiveness and providing cancellation/timeout guardrails.

### Approach

- Spawn a dedicated child process for the transcription run. Options:
  - `multiprocessing` with the "spawn" start method (default on macOS)
  - `subprocess` invoking a small module (e.g., `python -m podx.worker.transcribe`)
- Parent process (JobsService/WhisperRunner wrapper) remains responsive and can
  emit estimated, time‑based ticks while the child runs; if the child streams
  segments, pass those through as real progress updates.

### IPC Protocol

- Use newline‑delimited JSON over stdout/stderr from the child to the parent, or
  a `multiprocessing.Queue`/Pipe when using `multiprocessing`.
- Message shapes:
  - `{ "type": "progress", "percent": 35, "cur": 120, "total": 3600 }`
  - `{ "type": "log", "level": "info", "msg": "loading model…" }`
  - `{ "type": "result", "vtt": "/…/transcript.vtt", "txt": "/…/transcript.txt" }`
  - `{ "type": "error", "msg": "…" }`

### Lifecycle

- Parent starts child and begins a clock‑based ticker if `duration_sec > 0`.
- If the child sends segment progress, parent forwards those updates via
  `ProgressReporter` (overriding the estimate).
- On completion, parent publishes a final 100% and joins/cleans up.
- Cancellation: parent can terminate the child (SIGTERM/terminate) and emit a
  failed job status.

### Pros / Cons

- Pros:
  - Reliable UI updates unaffected by GIL or non‑yielding Python code
  - Better isolation; can kill stuck runs and reclaim memory
  - Clear logs via a separate process
- Cons:
  - Increased complexity (process management, IPC, error surfacing)
  - Slight overhead in startup and file handoff

### Implementation Notes

- Keep the service contract unchanged: `IngestionService` continues to return
  results and emit progress via `ProgressReporter`.
- Prefer `subprocess` first for minimal coupling; evolve to `multiprocessing`
  if structured objects over a queue are desired.
- Ensure the child process runs within the same virtualenv and receives the
  same `Config` (either serialize minimal settings or point it to the config
  file path via `PODX_CONFIG`).

