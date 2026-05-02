"""Reusable file-filter instructions for agents that scan Python source."""

PYTHON_SOURCE_FILTER = """\
## Source Code Only

Only analyze Python source files that are tracked by git. When
discovering files, prefer `git ls-files '*.py'` over Glob — this
automatically excludes `.venv/`, `__pycache__/`, `dist/`, and anything
in `.gitignore`. Also skip configuration, generated files, lock files,
and documentation: `poetry.lock`, `*.pyc`, `*.egg-info/`,
`*.generated.*`, `*.md`, `*.rst`."""
