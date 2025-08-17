# podx

A minimal Python command-line tool scaffold.

## Install (editable for development)

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate
pip install -e .
```

## Usage

- Show help: `podx --help`
- Show version: `podx --version`

You can also run as a module: `python -m podx --help`.

## Project Layout

- `pyproject.toml`: Package metadata and console script entrypoint
- `src/podx/cli.py`: CLI entrypoint implementation
- `src/podx/__init__.py`: Package metadata (version)
- `src/podx/__main__.py`: Enables `python -m podx`

## License

MIT

