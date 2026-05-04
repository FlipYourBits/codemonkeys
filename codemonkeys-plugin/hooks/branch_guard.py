"""UserPromptSubmit hook — block prompts on protected branches, suggest feature branch."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PREFIX_MAP: dict[str, str] = {
    "fix": "fix/",
    "bug": "fix/",
    "patch": "fix/",
    "hotfix": "fix/",
    "refactor": "refactor/",
    "restructure": "refactor/",
    "cleanup": "refactor/",
    "docs": "docs/",
    "document": "docs/",
    "test": "test/",
    "tests": "test/",
    "chore": "chore/",
    "ci": "chore/",
    "build": "chore/",
}

NOISE_WORDS = frozenset(
    ["the", "a", "an", "to", "for", "on", "in", "with", "and", "or", "is", "it", "this", "that"]
)

DEFAULT_PROTECTED = frozenset(["main", "master"])


def _infer_branch_name(prompt: str) -> str:
    cleaned = re.sub(r"/\S+:\S+", "", prompt).strip()

    words = cleaned.lower().split()
    if not words:
        return "feat/unnamed-branch"

    prefix = "feat/"
    if words[0] in PREFIX_MAP:
        prefix = PREFIX_MAP[words[0]]
        words = words[1:]

    words = [w for w in words if w not in NOISE_WORDS]

    slug = re.sub(r"[^a-z0-9]+", "-", " ".join(words))
    slug = slug.strip("-")

    if not slug:
        return "feat/unnamed-branch"

    if len(slug) > 50:
        cut = slug[:50].rfind("-")
        slug = slug[: cut if cut > 0 else 50]

    return f"{prefix}{slug}"


def _get_protected_branches(cwd: Path) -> set[str]:
    protected = set(DEFAULT_PROTECTED)
    config_path = cwd / ".codemonkeys" / "config.json"
    if not config_path.exists():
        return protected
    try:
        config = json.loads(config_path.read_text())
        extras = config.get("protected_branches", [])
        if isinstance(extras, list):
            protected.update(str(b) for b in extras)
    except (json.JSONDecodeError, OSError):
        pass
    return protected


def _is_git_repo(cwd: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode == 0


def _current_branch(cwd: Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip()


def main() -> None:
    data = json.loads(sys.stdin.read())
    prompt = data.get("prompt", "")
    cwd = Path(data.get("cwd", ".")).resolve()

    if not _is_git_repo(cwd):
        sys.exit(0)

    branch = _current_branch(cwd)
    if not branch:
        sys.exit(0)

    protected = _get_protected_branches(cwd)
    if branch not in protected:
        sys.exit(0)

    suggested = _infer_branch_name(prompt)
    print(
        f"[codemonkeys] You're on '{branch}' (protected branch).\n"
        f"Suggested branch: git checkout -b {suggested}\n"
        f"Create the branch and resubmit, or switch to an existing feature branch."
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
