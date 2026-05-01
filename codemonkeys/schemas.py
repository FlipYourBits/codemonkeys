"""Output schemas for structured agent results.

These are plain JSON Schema dicts passed to `output_format` when running
agents standalone via `AgentRunner`. They are NOT used when agents run
as subagents dispatched by a coordinator (the SDK ignores `output_format`
on subagents).
"""

from __future__ import annotations

FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "file": {"type": "string"},
        "line": {"type": ["integer", "null"]},
        "severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "category": {"type": "string"},
        "description": {"type": "string"},
        "recommendation": {"type": "string"},
    },
    "required": ["file", "severity", "category", "description", "recommendation"],
}

REVIEW_RESULT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": FINDING_SCHEMA,
            },
            "summary": {"type": "string"},
        },
        "required": ["findings", "summary"],
    },
}

TOOL_RESULT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "tool": {"type": "string"},
            "exit_code": {"type": "integer"},
            "output": {"type": "string"},
            "errors": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "line": {"type": ["integer", "null"]},
                        "message": {"type": "string"},
                    },
                    "required": ["file", "message"],
                },
            },
            "summary": {"type": "string"},
        },
        "required": ["tool", "exit_code", "output", "summary"],
    },
}

WRITER_RESULT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "files_created": {
                "type": "array",
                "items": {"type": "string"},
            },
            "files_modified": {
                "type": "array",
                "items": {"type": "string"},
            },
            "skipped": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["item", "reason"],
                },
            },
            "tests_pass": {"type": "boolean"},
            "summary": {"type": "string"},
        },
        "required": ["files_created", "files_modified", "summary"],
    },
}

FIX_RESULT_SCHEMA = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "fixed": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "line": {"type": ["integer", "null"]},
                        "description": {"type": "string"},
                    },
                    "required": ["file", "description"],
                },
            },
            "skipped": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "line": {"type": ["integer", "null"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["file", "reason"],
                },
            },
            "tests_pass": {"type": "boolean"},
            "summary": {"type": "string"},
        },
        "required": ["fixed", "skipped", "tests_pass", "summary"],
    },
}
