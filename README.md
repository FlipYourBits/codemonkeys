# codemonkeys

Deterministic skill-driven workflows for Python development in [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Provides structured code review, feature implementation with TDD, and architecture documentation — all as Claude Code plugin skills.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- Python 3.10+
- For filesystem sandboxing on Linux: `pip install landlock` (kernel 5.13+)

## Installation

Install the plugin from the codemonkeys-plugin directory:

```bash
claude plugin add /path/to/codemonkeys/codemonkeys-plugin
```

## Skills

### python-review

Full Python code review with mechanical checks and manual review checklists.

```
/codemonkeys:python-review
```

Runs up to 9 review categories: quality, security, type checking (mypy), tests (pytest), coverage, linting (ruff), dependency audit (pip-audit), changelog review, and README review. Presents findings with severity and recommendations, then fixes approved issues.

### python-feature

Design-to-implementation workflow for new Python features.

```
/codemonkeys:python-feature
```

Walks through clarifying questions, design approaches, and a plan document. Once the plan is approved, dispatches the `python-implementer` agent to implement with TDD, then verifies with ruff, mypy, and pytest.

### project-architecture

Builds and maintains a `docs/architecture.md` file — a comprehensive snapshot of the project.

```
/codemonkeys:project-architecture
```

Tracks freshness via a commit hash. On first run it documents the full project; on subsequent runs it incrementally updates only what changed.

## Agent

### python-implementer

Implements features, updates, and bug fixes from an approved plan file using TDD. Dispatched by the `python-feature` skill — not invoked directly. Reads the plan, writes failing tests first, then implements the code to make them pass.

## Filesystem Sandbox

`sandbox.py` is a standalone module that restricts filesystem writes to the project directory at the OS level. Call `restrict()` once at startup — the restriction is irrevocable for the process lifetime.

```python
from sandbox import restrict

restrict("/path/to/project")
```

Supported platforms:

| Platform | Backend | Dependency |
|----------|---------|------------|
| Linux | Landlock LSM | `pip install landlock` (kernel 5.13+) |
| macOS | sandbox-exec / Seatbelt | None (built-in) |
| Windows | Low Integrity Token | None (built-in) |

## Hooks

The plugin includes 6 Claude Code hooks that automate deterministic checks. These activate when the plugin is installed — no additional configuration needed.

| Hook | Event | What it does |
|------|-------|-------------|
| Check runner | UserPromptSubmit | Runs ruff, mypy, pytest, pip-audit before code review |
| Command guard | PreToolUse | Blocks destructive commands (rm -rf, force push, etc.) |
| Auto-formatter | PostToolUse | Runs ruff fix + format on Python files after each edit |
| Quality gate | Stop | Blocks completion if tests are failing (max 2 attempts) |
| Session init | SessionStart | Injects git branch/status, cleans up stale artifacts |
| Failure logger | PostToolUseFailure | Logs failed tool calls to `.codemonkeys/logs/failures.jsonl` |

### Opt-in write sandbox

For additional protection, create `.codemonkeys/config.json` in your project:

```json
{
  "sandbox": true
}
```

This blocks Edit/Write operations on files outside the project directory.

## Debugging & Observability

To see everything Claude Code is doing (tool calls, file reads, API requests), set these env vars before launching:

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_LOGS_EXPORTER=console
export OTEL_LOG_TOOL_DETAILS=1      # tool names, file paths, bash commands
export OTEL_LOG_TOOL_CONTENT=1      # full tool input/output
```

For quick one-off debugging:

```bash
claude --debug                        # debug output to console
claude --debug-file /tmp/claude.log   # write to file
claude --verbose                      # verbose turn-by-turn output
```

## License

[MIT](LICENSE)
