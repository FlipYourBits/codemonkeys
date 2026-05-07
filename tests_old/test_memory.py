from __future__ import annotations

import json
from pathlib import Path

from codemonkeys.core.memory import MemoryBackend


class TestMemoryBackend:
    def test_create_and_view(self, tmp_path: Path) -> None:
        backend = MemoryBackend(tmp_path)
        backend.create("progress.json", '{"files_done": []}')
        content = backend.view("progress.json")
        assert json.loads(content) == {"files_done": []}

    def test_view_nonexistent_returns_none(self, tmp_path: Path) -> None:
        backend = MemoryBackend(tmp_path)
        assert backend.view("nonexistent.json") is None

    def test_str_replace(self, tmp_path: Path) -> None:
        backend = MemoryBackend(tmp_path)
        backend.create("notes.md", "hello world")
        backend.str_replace("notes.md", "hello", "goodbye")
        content = backend.view("notes.md")
        assert content == "goodbye world"

    def test_str_replace_nonexistent_raises(self, tmp_path: Path) -> None:
        import pytest

        backend = MemoryBackend(tmp_path)
        with pytest.raises(FileNotFoundError):
            backend.str_replace("missing.md", "a", "b")

    def test_delete(self, tmp_path: Path) -> None:
        backend = MemoryBackend(tmp_path)
        backend.create("temp.json", "{}")
        backend.delete("temp.json")
        assert backend.view("temp.json") is None

    def test_delete_nonexistent_is_noop(self, tmp_path: Path) -> None:
        backend = MemoryBackend(tmp_path)
        backend.delete("nonexistent.json")

    def test_list_files(self, tmp_path: Path) -> None:
        backend = MemoryBackend(tmp_path)
        backend.create("a.json", "{}")
        backend.create("b.json", "{}")
        backend.create("subdir/c.json", "{}")
        files = backend.list_files()
        assert "a.json" in files
        assert "b.json" in files
        assert "subdir/c.json" in files

    def test_path_traversal_blocked(self, tmp_path: Path) -> None:
        import pytest

        backend = MemoryBackend(tmp_path)
        with pytest.raises(ValueError, match="outside memory"):
            backend.create("../../etc/passwd", "bad")

    def test_create_nested_directory(self, tmp_path: Path) -> None:
        backend = MemoryBackend(tmp_path)
        backend.create("deep/nested/file.json", '{"ok": true}')
        content = backend.view("deep/nested/file.json")
        assert json.loads(content) == {"ok": True}
