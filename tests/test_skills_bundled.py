from __future__ import annotations

import importlib.resources as resources


def test_bundled_skills_present():
    pkg = resources.files("langclaude.skills")
    names = {p.name for p in pkg.iterdir() if p.name.endswith(".md")}
    assert {
        "python-clean-code.md",
        "python-security.md",
        "git-guidelines.md",
    }.issubset(names)


def test_bundled_skills_nonempty():
    pkg = resources.files("langclaude.skills")
    for name in ("python-clean-code.md", "python-security.md", "git-guidelines.md"):
        text = (pkg / name).read_text(encoding="utf-8")
        assert len(text) > 100, f"{name} looks too short"
