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

## Project Layout

- `pyproject.toml`: Package metadata and console script entrypoint
- `src/podx/cli.py`: CLI entrypoint implementation
- `src/podx/__init__.py`: Package metadata (version)
- `src/podx/__main__.py`: Enables `python -m podx`

## License

MIT

