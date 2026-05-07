"""Read/write/list structured artifacts in .codemonkeys/ directories."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def new_run(self, workflow: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        base_run_id = f"{workflow}/{ts}"
        run_id = base_run_id
        counter = 1
        while (self._root / run_id).exists():
            run_id = f"{base_run_id}-{counter}"
            counter += 1
        run_dir = self._root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_id

    def save(self, run_id: str, name: str, artifact: BaseModel) -> Path:
        path = self._root / run_id / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(artifact.model_dump_json(indent=2))
        return path

    def load(self, run_id: str, name: str, model: type[T]) -> T | None:
        path = self._root / run_id / f"{name}.json"
        if not path.exists():
            return None
        return model.model_validate_json(path.read_text())

    def list_runs(self, workflow: str) -> list[str]:
        workflow_dir = self._root / workflow
        if not workflow_dir.is_dir():
            return []
        return sorted(
            [f"{workflow}/{d.name}" for d in workflow_dir.iterdir() if d.is_dir()],
            reverse=True,
        )

    def list_artifacts(self, run_id: str, subdirectory: str = "") -> list[str]:
        target = self._root / run_id
        if subdirectory:
            target = target / subdirectory
        if not target.is_dir():
            return []
        return sorted(p.stem for p in target.glob("*.json"))
