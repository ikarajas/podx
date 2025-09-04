# podx

`podx` is a command‑line tool for working with podcasts.  It can transcribe
episodes using Whisper and search online directories for new shows to follow.

## Install (editable for development)

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate
pip install -e .
```

## CLI Usage

`podx` exposes three sub‑commands:

* **Transcribe an episode**

  ```bash
  podx ingest --audio /path/to/file.mp3 [--podcast "Podcast"] [--episode "Title"]
  ```

* **Search for podcasts**

  ```bash
  podx search "history"
  ```

* **Launch the graphical interface**

  ```bash
  podx ui
  ```

Run `podx --help` or `podx <command> --help` for full options.  The tool can
also be invoked as a module: `python -m podx`.

## Configuration

Runtime configuration is read from `~/.podx/config.yaml` (or the file pointed to
by the `PODX_CONFIG` environment variable).  See [AGENTS.md](AGENTS.md) for a
deeper look at the project architecture and contribution guidelines.

### Cross-platform Whisper engines

Podx supports multiple transcription engines via a single runner:

- macOS arm64: uses MLX (`mlx_whisper`) by default for best performance.
- Windows/Linux (or non‑arm64 macOS): uses OpenAI Whisper CLI (`whisper`).

You can override the engine and model in your config file:

```yaml
whisper:
  runner: whisper   # or "mlx" on macOS arm64
  model: small.en   # e.g., "base", "small.en", etc.
  extra_args: ["--language", "en"]
```

Note: Both engines require FFmpeg to be installed and available on `PATH`.

### Performance: Faster-Whisper (Intel-friendly)

On Windows/Linux or Intel iGPUs, you can use Faster‑Whisper for better speed, with optional OpenVINO GPU acceleration:

- Install extras: `pip install -e .[faster]` (or `pip install faster-whisper`)
- Set config:

```yaml
whisper:
  runner: faster
  model: small.en
  extra_args: ["--language", "en"]
```

- Optional env for OpenVINO GPU: set `CT2_USE_OPENVINO=1` and `OPENVINO_DEVICE=GPU` (e.g., `GPU.0`). You can also tune with `PODX_FASTER_DEVICE` and `PODX_FASTER_COMPUTE`.
  Podx uses Faster‑Whisper without VAD by default to keep dependencies light; no extra packages are required.

### Feed metadata cache and subscription keys

The UI caches podcast channel metadata (title, description, icon) per
subscription to keep the subscriptions list fast. This cache lives in
`feeds_meta.json` under your configured `root_dir` and is keyed by a stable,
human‑readable subscription key of the form `slug--shortid` (derived from the
podcast title and a digest of the feed URL). See the detailed docs in
[`docs/feeds-metadata.md`](docs/feeds-metadata.md).

### Episode index and transcription status

Transcription status is tracked per subscription in a lightweight JSON index so
the UI can show which episodes are already transcribed without re-reading media.
The index lives under each subscription directory and is keyed using stable
identifiers (GUID/enclosure URL with fallbacks). See
[`docs/episodes-index.md`](docs/episodes-index.md).

### UI: Tabbed Episode Pane

The graphical interface includes an enhanced, two‑pane episode view:

- Left: a fast, uniform list of episodes with inline status icons. Clicking the
  icon starts transcription for that episode.
- Right: an episode detail header (artwork, title, date, duration, description)
  above a tabbed pane:
  - Transcript tab: shows transcript text when available, along with a header
    timestamp sourced from the episode index (`updated_at` falling back to
    `created_at`). A Regenerate button re‑runs transcription for the selected
    episode (same handler as the list icon).
  - Summary tab: placeholder for future summaries with its own Regenerate
    button. When summaries are implemented, the UI will read `summary_path` and
    `summary_updated_at` from the episode index.

Under the hood, the episode view consults `episodes_index.json` for each
subscription key to:

- Mark items as transcribed/failed without re‑reading media.
- Locate transcript files (`txt_path`, `vtt_path`) and show generation
  timestamps.
- Keep transcript and summary timestamps independent so regeneration of one
  does not clobber the other.

## Project Layout

- `pyproject.toml`: Package metadata and console script entrypoint
- `src/podx/cli.py`: CLI entrypoint implementation
- `src/podx/__init__.py`: Package metadata (version)
- `src/podx/__main__.py`: Enables `python -m podx`

## License

MIT
