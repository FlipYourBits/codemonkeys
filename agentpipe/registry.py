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
    from agentpipe.nodes.code_review import code_review_node
    from agentpipe.nodes.dependency_audit import dependency_audit_node
    from agentpipe.nodes.python_dependency_audit import python_dependency_audit_node
    from agentpipe.nodes.docs_review import docs_review_node
    from agentpipe.nodes.git_commit import git_commit_node
    from agentpipe.nodes.git_new_branch import git_new_branch_node
    from agentpipe.nodes.implement_feature import implement_feature_node
    from agentpipe.nodes.python_coverage import python_coverage_node
    from agentpipe.nodes.python_implement_feature import python_implement_feature_node
    from agentpipe.nodes.python_plan_feature import python_plan_feature_node
    from agentpipe.nodes.python_test import python_test_node
    from agentpipe.nodes.python_format import python_format_node
    from agentpipe.nodes.python_lint import python_lint_node
    from agentpipe.nodes.resolve_findings import resolve_findings_node
    from agentpipe.nodes.security_audit import security_audit_node

    _BUILTINS.update(
        {
            "git_new_branch": git_new_branch_node,
            "git_commit": git_commit_node,
            "implement_feature": implement_feature_node,
            "python_implement_feature": python_implement_feature_node,
            "python_plan_feature": python_plan_feature_node,
            "code_review": code_review_node,
            "security_audit": security_audit_node,
            "docs_review": docs_review_node,
            "python_lint": python_lint_node,
            "python_format": python_format_node,
            "python_test": python_test_node,
            "python_coverage": python_coverage_node,
            "dependency_audit": dependency_audit_node,
            "python_dependency_audit": python_dependency_audit_node,
            "resolve_findings": resolve_findings_node,
        }
    )


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
            f"{name!r} not found in built-in registry. Available: {sorted(_BUILTINS)}"
        )
    return _BUILTINS[name]


def list_builtins() -> list[str]:
    """Return sorted list of built-in node names."""
    _ensure_builtins()
    return sorted(_BUILTINS)


def list_registered() -> list[str]:
    """Return sorted list of user-registered node names."""
    return sorted(_USER_REGISTRY)
