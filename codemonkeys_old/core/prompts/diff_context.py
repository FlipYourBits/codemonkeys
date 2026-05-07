"""Diff mode context template — injected into file reviewer prompts."""

DIFF_CONTEXT_TEMPLATE = """\
## What Changed (diff context)

These files were modified in this branch. Here are the relevant hunks:

{diff_hunks}

## Call Graph (blast radius)

Functions modified and their direct callers:

{call_graph}

## Focus

Prioritize reviewing the CHANGED code and its interactions. Existing code
that was not touched is only relevant if the changes broke an assumption
it depends on."""
