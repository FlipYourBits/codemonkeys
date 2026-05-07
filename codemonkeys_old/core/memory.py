"""Memory Tool backend — file-based persistence for agent compaction resilience."""

from __future__ import annotations

from pathlib import Path


class MemoryBackend:
    """Simple file-based memory store scoped to a directory.

    All paths are relative to the root directory. Path traversal
    outside the root is rejected.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _resolve(self, path: str) -> Path:
        resolved = (self._root / path).resolve()
        if not resolved.is_relative_to(self._root):
            msg = f"Path {path!r} resolves outside memory root"
            raise ValueError(msg)
        return resolved

    def view(self, path: str) -> str | None:
        target = self._resolve(path)
        if not target.exists():
            return None
        return target.read_text()

    def create(self, path: str, content: str) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def str_replace(self, path: str, old: str, new: str) -> None:
        target = self._resolve(path)
        if not target.exists():
            msg = f"File {path!r} does not exist"
            raise FileNotFoundError(msg)
        text = target.read_text()
        target.write_text(text.replace(old, new))

    def delete(self, path: str) -> None:
        target = self._resolve(path)
        if target.exists():
            target.unlink()

    def list_files(self) -> list[str]:
        if not self._root.exists():
            return []
        return sorted(
            str(p.relative_to(self._root)) for p in self._root.rglob("*") if p.is_file()
        )
