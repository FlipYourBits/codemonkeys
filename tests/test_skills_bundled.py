from __future__ import annotations

from codemonkeys.skills import (
    JAVASCRIPT_CLEAN_CODE,
    JAVASCRIPT_SECURITY,
    PYTHON_CLEAN_CODE,
    PYTHON_SECURITY,
    RUST_CLEAN_CODE,
    RUST_SECURITY,
)

ALL_SKILLS = [
    JAVASCRIPT_CLEAN_CODE,
    JAVASCRIPT_SECURITY,
    PYTHON_CLEAN_CODE,
    PYTHON_SECURITY,
    RUST_CLEAN_CODE,
    RUST_SECURITY,
]


def test_bundled_skills_are_nonempty_strings():
    for skill in ALL_SKILLS:
        assert isinstance(skill, str)
        assert len(skill) > 100
