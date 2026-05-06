# Agent Testing Cheat Sheet

Run each agent independently to verify behavior, guardrails, and output quality.

After each run, check:

| What to check | Where |
|---|---|
| Did it call the right tools in a sensible order? | Terminal output (tool trace) |
| Did it respect guardrails (no git, no pip, no Write on read-only agents)? | Terminal -- any unexpected tool calls |
| Is the structured JSON valid and complete? | Panel at the end |
| Did it stay in scope (no extra files, no drive-by fixes)? | The `.md` log in the printed log dir |
| Full raw event stream + token usage per turn | The `.log` file (JSONL) |

---

## 1. python_file_reviewer

Most-dispatched agent. Test with a non-trivial prod file and a test file on haiku.

```bash
uv run python -m codemonkeys.run_agent python_file_reviewer --files codemonkeys/core/runner.py --resilience --test-quality --audit
```

## 2. changelog_reviewer

No args needed. Verifies CHANGELOG.md against git history.

```bash
uv run python -m codemonkeys.run_agent changelog_reviewer --audit
```

## 3. readme_reviewer

No args needed. Verifies README.md claims against the codebase.

```bash
uv run python -m codemonkeys.run_agent readme_reviewer --audit
```

## 4. architecture_reviewer

Give it 3-5 related files. AST metadata is generated automatically.

```bash
uv run python -m codemonkeys.run_agent architecture_reviewer --files codemonkeys/core/runner.py codemonkeys/core/_runner_helpers.py codemonkeys/core/run_result.py codemonkeys/workflows/phase_library/review.py --audit
```

## 5. python_characterization_tester

Pick a file with low/no test coverage.

```bash
uv run python -m codemonkeys.run_agent python_characterization_tester --files codemonkeys/core/analysis.py --audit
```

## 6. python_code_fixer

Run file_reviewer first, then feed one or more findings from its output.

```bash
cat > /tmp/findings.json << 'EOF'
[
  {
    "file": "codemonkeys/core/runner.py",
    "line": 26,
    "severity": "low",
    "category": "quality",
    "subcategory": "code_structure",
    "title": "Logger defined before local imports",
    "description": "_log is defined between stdlib and local imports",
    "suggestion": "Move _log = logging.getLogger(__name__) after all imports"
  }
]
EOF

uv run python -m codemonkeys.run_agent python_code_fixer --files codemonkeys/core/runner.py --prompt-file /tmp/findings.json --audit
```

## 7. python_structural_refactorer

Give it files and a concrete problem description.

```bash
uv run python -m codemonkeys.run_agent python_structural_refactorer --files codemonkeys/core/runner.py codemonkeys/core/_runner_helpers.py --prompt "runner.py defines _log between stdlib and local imports, which triggers E402. Move all local imports above _log." --refactor-type extract_shared --audit
```

## 8. python_implementer

Point it at an existing plan file, or write a small throwaway one.

```bash
cat > /tmp/test-plan.md << 'EOF'
# Plan: Add __version__ to codemonkeys package

## Steps

1. Add `__version__ = "0.1.0"` to `codemonkeys/__init__.py`
2. Add a test in `tests/test_version.py` that imports and asserts the version string
EOF

uv run python -m codemonkeys.run_agent python_implementer --prompt-file /tmp/test-plan.md --audit
```

## 9. spec_compliance_reviewer

Needs a JSON spec file and the implementation files to check against.

```bash
cat > /tmp/test-spec.json << 'EOF'
{
  "title": "Add __version__",
  "description": "Expose package version",
  "steps": [
    {"description": "Add __version__ to __init__.py", "files": ["codemonkeys/__init__.py"]},
    {"description": "Add version test", "files": ["tests/test_version.py"]}
  ]
}
EOF

uv run python -m codemonkeys.run_agent spec_compliance_reviewer --files codemonkeys/__init__.py tests/test_version.py --prompt-file /tmp/test-spec.json --audit
```

## 10. agent_auditor (direct)

The `--audit` flag above handles most cases. For running the auditor directly against an existing log:

```bash
uv run python -m codemonkeys.run_agent agent_auditor \
  --agent-source codemonkeys/core/agents/changelog_reviewer.py \
  --prompt-file .codemonkeys/logs/<timestamp>/changelog_reviewer_<timestamp>.log
```

You can also audit all agents after a full review workflow:

```bash
uv run python -m codemonkeys.run_review --diff --audit
```

After the audit panel appears you'll see numbered issues and recommendations. Enter numbers (e.g. `1,3`), `all`, or `skip`. Selecting items spawns a fixer agent that edits the target agent's prompt/tools/config.

---

## Recommended order

Start with **python_file_reviewer** and **changelog_reviewer** since they're the most-dispatched agents in the pipeline, then work through the rest. The tool trace in the terminal will immediately show if an agent is doing something unexpected.
