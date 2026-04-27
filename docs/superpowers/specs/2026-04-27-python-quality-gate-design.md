# Python Quality Gate Graph

A standalone sequential pipeline that runs all quality checks on existing code without creating branches, implementing features, or committing.

## Steps (sequential)

1. `python_lint` — lint and fix
2. `python_format` — format and fix
3. `python_test` — run tests
4. `python_coverage` — measure coverage
5. `code_review` — review and fix
6. `security_audit` — audit and fix
7. `docs_review` — review and fix
8. `dependency_audit` — audit and fix
9. `python_lint` (deduped to `python_lint_2`) — final lint

## CLI Interface

```
python -m langclaude.graphs.python_quality_gate <working_dir> [options]
```

| Arg | Type | Default | Description |
|-----|------|---------|-------------|
| `working_dir` | positional | required | Path to repo root |
| `--mode` | `full` or `diff` | `full` | Scan entire repo or only changes vs base ref |
| `--base-ref` | string | `main` | Git ref for diff mode |
| `--verbosity` | `silent`, `normal`, `verbose` | `normal` | Output verbosity |

## Config Logic

- `--mode full`: no per-node config overrides.
- `--mode diff`: pass `{"mode": "diff"}` to `python_coverage`, `code_review`, `security_audit`, `docs_review`. Pass `base_ref` into `extra_state`.

## Output

Print summary: test results, coverage, and cost. Same pattern as `python_new_feature.py`.

## File

`src/langclaude/graphs/python_quality_gate.py` — follows the same structure as `python_new_feature.py` using `Pipeline`.
