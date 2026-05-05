"""Agent factories for Claude Agent SDK workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codemonkeys.core.agents.changelog_reviewer import (
        make_changelog_reviewer as make_changelog_reviewer,
    )
    from codemonkeys.core.agents.python_file_reviewer import (
        make_python_file_reviewer as make_python_file_reviewer,
    )
    from codemonkeys.core.agents.python_implementer import (
        make_python_implementer as make_python_implementer,
    )
    from codemonkeys.core.agents.readme_reviewer import (
        make_readme_reviewer as make_readme_reviewer,
    )

__all__ = [
    "make_changelog_reviewer",
    "make_python_file_reviewer",
    "make_python_implementer",
    "make_readme_reviewer",
]


def __getattr__(name: str) -> object:
    if name == "make_changelog_reviewer":
        from codemonkeys.core.agents.changelog_reviewer import make_changelog_reviewer

        return make_changelog_reviewer
    if name == "make_python_file_reviewer":
        from codemonkeys.core.agents.python_file_reviewer import (
            make_python_file_reviewer,
        )

        return make_python_file_reviewer
    if name == "make_python_implementer":
        from codemonkeys.core.agents.python_implementer import make_python_implementer

        return make_python_implementer
    if name == "make_readme_reviewer":
        from codemonkeys.core.agents.readme_reviewer import make_readme_reviewer

        return make_readme_reviewer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
