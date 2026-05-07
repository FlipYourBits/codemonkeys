from __future__ import annotations

from pathlib import Path

import pytest

from codemonkeys.artifacts.schemas.findings import FileFindings, Finding
from codemonkeys.artifacts.store import ArtifactStore


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(tmp_path / ".codemonkeys")


@pytest.fixture
def sample_findings() -> FileFindings:
    return FileFindings(
        file="src/auth.py",
        summary="Auth module.",
        findings=[
            Finding(
                file="src/auth.py",
                line=42,
                severity="high",
                category="security",
                subcategory="injection",
                title="SQL injection",
                description="Unsafe query.",
                suggestion="Use parameterized queries.",
            ),
        ],
    )


class TestArtifactStore:
    def test_save_and_load(
        self, store: ArtifactStore, sample_findings: FileFindings
    ) -> None:
        run_id = store.new_run("review")
        store.save(run_id, "findings/src__auth.py", sample_findings)
        loaded = store.load(run_id, "findings/src__auth.py", FileFindings)
        assert loaded == sample_findings

    def test_list_runs(
        self, store: ArtifactStore, sample_findings: FileFindings
    ) -> None:
        run1 = store.new_run("review")
        store.save(run1, "findings/a", sample_findings)
        run2 = store.new_run("review")
        store.save(run2, "findings/b", sample_findings)
        runs = store.list_runs("review")
        assert len(runs) >= 2

    def test_list_artifacts_in_run(
        self, store: ArtifactStore, sample_findings: FileFindings
    ) -> None:
        run_id = store.new_run("review")
        store.save(run_id, "findings/file_a", sample_findings)
        store.save(run_id, "findings/file_b", sample_findings)
        artifacts = store.list_artifacts(run_id, "findings")
        assert len(artifacts) == 2

    def test_load_nonexistent_returns_none(self, store: ArtifactStore) -> None:
        loaded = store.load("nonexistent", "nope", FileFindings)
        assert loaded is None

    def test_root_dir_created_on_save(self, tmp_path: Path) -> None:
        root = tmp_path / "sub" / ".codemonkeys"
        store = ArtifactStore(root)
        findings = FileFindings(file="x.py", summary="x", findings=[])
        run_id = store.new_run("review")
        store.save(run_id, "test", findings)
        assert root.is_dir()
