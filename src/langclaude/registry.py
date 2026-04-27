"""Node registry: maps string names to node factory callables.

Built-in nodes are bare strings (no slash). User-registered nodes require
a namespace prefix (e.g. "custom/my_node", "acme/deploy"). Resolution:
no "/" -> built-in lookup; has "/" -> user registry lookup.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_BUILTINS: dict[str, Callable[..., Any]] = {}
_USER_REGISTRY: dict[str, Callable[..., Any]] = {}


def _register_builtins() -> None:
    from langclaude.nodes.branch_namer import claude_new_branch_node
    from langclaude.nodes.code_review import claude_code_review_node
    from langclaude.nodes.dependency_audit import claude_dependency_audit_node
    from langclaude.nodes.docs_review import claude_docs_review_node
    from langclaude.nodes.feature_implementer import claude_feature_implementer_node
    from langclaude.nodes.ruff_node import shell_ruff_fix_node, shell_ruff_fmt_node
    from langclaude.nodes.security_audit import claude_security_audit_node
    from langclaude.nodes.test_coverage import claude_coverage_node
    from langclaude.nodes.test_runner import claude_pytest_node

    _BUILTINS.update({
        "new_branch": claude_new_branch_node,
        "implement_feature": claude_feature_implementer_node,
        "code_review": claude_code_review_node,
        "security_audit": claude_security_audit_node,
        "docs_review": claude_docs_review_node,
        "ruff_fix": shell_ruff_fix_node,
        "ruff_fmt": shell_ruff_fmt_node,
        "pytest": claude_pytest_node,
        "coverage": claude_coverage_node,
        "dependency_audit": claude_dependency_audit_node,
    })


def _ensure_builtins() -> None:
    if not _BUILTINS:
        _register_builtins()


def register(
    name: str,
    node: Callable[..., Any],
    *,
    namespace: str = "custom",
) -> None:
    """Register a user-defined node under namespace/name."""
    if "/" in name:
        raise ValueError(
            f"name must not contain '/': {name!r}. "
            f"Pass the namespace separately via namespace="
        )
    _USER_REGISTRY[f"{namespace}/{name}"] = node


def resolve(name: str) -> Callable[..., Any]:
    """Look up a node by registry name.

    Bare names (no "/") resolve from built-ins. Namespaced names
    resolve from the user registry. Raises KeyError if not found.
    """
    if "/" in name:
        if name not in _USER_REGISTRY:
            raise KeyError(
                f"{name!r} not found in user registry. "
                f"Registered: {sorted(_USER_REGISTRY)}"
            )
        return _USER_REGISTRY[name]

    _ensure_builtins()
    if name not in _BUILTINS:
        raise KeyError(
            f"{name!r} not found in built-in registry. "
            f"Available: {sorted(_BUILTINS)}"
        )
    return _BUILTINS[name]


def list_builtins() -> list[str]:
    """Return sorted list of built-in node names."""
    _ensure_builtins()
    return sorted(_BUILTINS)


def list_registered() -> list[str]:
    """Return sorted list of user-registered node names."""
    return sorted(_USER_REGISTRY)
