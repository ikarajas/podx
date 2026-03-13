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

`podx` exposes several sub‑commands:

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

* **Summarize a transcript**

  ```bash
  # From a file (uses provider configured in config.yaml, default: Gemini)
  podx summarize --file transcript.txt

  # Override provider or model
  podx summarize -f transcript.txt --provider anthropic --model claude-3-5-haiku-20241022

  # From stdin, save to file
  cat transcript.txt | podx summarize -f - --out summary.txt

  # Using local Ollama
  podx summarize -f transcript.txt --provider ollama
  ```

  The active provider is configured in `config.yaml`. API keys come from environment variables (never stored on disk).

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

### LLM configuration (summarization)

Summarization uses a pluggable backend. The default provider is **Google Gemini** (`gemini-2.5-flash`). Supported providers: Gemini, Anthropic, OpenAI, and Ollama (local). Only install the package for the provider you want to use.

API keys are **never** written to disk — they are read from environment variables at runtime.

#### Setting up with Google Gemini

1. **Install the Gemini package:**

   ```bash
   pip install -e '.[gemini]'
   ```

2. **Set your API key.** Get one from [Google AI Studio](https://aistudio.google.com/apikey), then export it in your shell (add to `~/.zshrc` or `~/.bashrc` to make it permanent):

   ```bash
   export GEMINI_API_KEY=your_key_here
   ```

3. **Add the provider to your config file** (`~/.podx/config.yaml`). Create the file if it does not exist:

   ```yaml
   root_dir: ~/podx        # where episodes and transcripts are stored
   llm:
     provider: gemini
   ```

   That is all that is required. Gemini defaults to `gemini-2.5-flash`; set `model: gemini-2.5-flash-lite` (cheaper) or `gemini-2.5-pro` (more capable) under `llm:` to override.

4. **Verify it works:**

   ```bash
   echo "Alice and Bob discussed machine learning over coffee." | podx summarize -f -
   ```

#### Setting up with Ollama (local, no API key)

Ollama runs models on your own machine — no API key or internet connection needed after the initial model download.

1. **Install Ollama** from [ollama.com](https://ollama.com) and start it:

   ```bash
   ollama serve          # starts the local server (runs in background)
   ollama pull llama3    # download the default model (~4 GB)
   ```

2. **No Python package is needed** — podx talks to Ollama over its local REST API using the standard library.

3. **Configure your config file** (`~/.podx/config.yaml`):

   ```yaml
   root_dir: ~/podx
   llm:
     provider: ollama
     ollama_host: http://localhost:11434   # default; change if Ollama runs elsewhere
     ollama_model: llama3                 # or any model you have pulled
   ```

4. **Verify it works:**

   ```bash
   echo "Alice and Bob discussed machine learning over coffee." | podx summarize -f -
   ```

#### Additional config options

```yaml
llm:
  timeout_sec: 60       # seconds before an LLM call times out
summarization:
  word_count: 175       # target summary length (default ~150-200 words)
```

#### Using summarization in the UI

Select a transcribed episode, open the **Summary** tab, and click **Regenerate**. The job runs in the background and appears in the Jobs view. Once complete the summary is shown immediately and cached to `{episode_dir}/summary.txt` — re-opening the episode will not call the LLM again unless you click Regenerate a second time.

### Performance: Faster-Whisper (Intel-friendly)

On Windows/Linux or Intel iGPUs, you can use Faster‑Whisper for better speed, with optional OpenVINO GPU acceleration:

- Install extras: `pip install -e '.[faster]'` (or `pip install faster-whisper`)
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
  - Summary tab: shows the cached summary when available. Click **Regenerate**
    to generate (or regenerate) a summary via the configured LLM provider.
    The job appears in the Jobs view while running. The result is cached to
    `{episode_dir}/summary.txt` and the episode index records `summary_path`
    and `summary_updated_at`.

Under the hood, the episode view consults `episodes_index.json` for each
subscription key to:

- Mark items as transcribed/failed without re‑reading media.
- Locate transcript files (`txt_path`, `vtt_path`) and show generation
  timestamps.
- Keep transcript and summary timestamps independent so regeneration of one
  does not clobber the other.

### Ingestion pipeline and progress

See `docs/ingestion-pipeline.md` for a walkthrough of the ingestion steps and
progress strategies. It also outlines an optional child‑process design to make
progress updates robust for runners that do not yield frequently (e.g., some
MLX configurations).

## Project Layout

- `pyproject.toml`: Package metadata and console script entrypoint
- `src/podx/cli.py`: CLI entrypoint implementation
- `src/podx/__init__.py`: Package metadata (version)
- `src/podx/__main__.py`: Enables `python -m podx`

## License

MIT
