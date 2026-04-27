# agentpipe

## Environment

- Python: `.venv/bin/python`
- Run tests: `.venv/bin/python -m pytest tests/ -x -q --no-header`

## Architecture

- Each node has a single responsibility and never depends on another node.
- Graphs with a `__main__` block must use `argparse` for CLI argument parsing.
