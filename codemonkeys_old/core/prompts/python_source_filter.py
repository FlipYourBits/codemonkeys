"""Reusable file-filter instructions for agents that scan Python source."""

PYTHON_SOURCE_FILTER = """\
## Source Code Only

Only analyze Python source files. Skip configuration, generated files,
lock files, documentation, and vendored dependencies. Files to SKIP:
`poetry.lock`, `*.pyc`, `*.egg-info/`, `__pycache__/`, `.venv/`,
`dist/`, `*.generated.*`, `*.md`, `*.rst`."""
