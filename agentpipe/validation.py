"""Pre-flight validation for graph composition.

`validate_node_outputs(*nodes)` walks nodes and raises if any output
key is written by ≥2 nodes. This
catches the classic footgun: two `code_review_node` instances both
defaulting to `review_findings`, with the second silently overwriting
the first.

A small allow-list of keys are designed to be written by multiple nodes
and reduced/summed by the consumer; those don't trigger the error.
"""

from __future__ import annotations

from typing import Any

# Keys that are *meant* to be written by many nodes — the consumer reduces.
MERGE_OK_KEYS: frozenset[str] = frozenset(
    {
        "last_cost_usd",  # summed across nodes
        "last_result",  # overwrites by design — many nodes write a freeform result
        "artifacts",  # users typically reduce dicts here
    }
)


class OutputKeyConflict(ValueError):
    """Raised when two nodes declare the same output key."""


def _outputs_of(node: Any) -> tuple[str, ...]:
    declared = getattr(node, "declared_outputs", None)
    if declared:
        return tuple(declared)
    return ()


def validate_node_outputs(*nodes: Any) -> None:
    """Raise OutputKeyConflict if any non-merge-OK key is claimed twice.

    Pass each node you added to the graph. The check is order-independent.
    Nodes without declared outputs are silently skipped (e.g. bare
    lambdas). For full coverage, ensure every node either has
    `declared_outputs: tuple[str, ...]` or `output_key: str` set.
    """
    seen: dict[str, list[str]] = {}
    for node in nodes:
        owner = (
            getattr(node, "name", None)
            or getattr(node, "__name__", None)
            or type(node).__name__
        )
        for key in _outputs_of(node):
            seen.setdefault(key, []).append(owner)

    conflicts = {
        key: owners
        for key, owners in seen.items()
        if len(owners) > 1 and key not in MERGE_OK_KEYS
    }
    if not conflicts:
        return

    lines = ["Output-key conflicts detected:"]
    for key, owners in conflicts.items():
        lines.append(f"  {key!r}: written by {', '.join(owners)}")
    lines.append("Set `output_key=` (or rename one node's output) to disambiguate.")
    raise OutputKeyConflict("\n".join(lines))
