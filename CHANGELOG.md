# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-04-27

### Added

- Pipeline orchestrator with sequential and parallel (`asyncio.gather`) step execution
- `ClaudeAgentNode` — wraps `claude_agent_sdk.query()` with per-node permissions, model selection, and skill injection
- `ShellNode` — runs subprocesses with streaming output and timeout support
- Node-level `reads_from` for selective upstream output injection (token-cost control)
- Per-node cost tracking with budget caps, warning thresholds, and run logs (`.codemonkeys/runs/`)
- Rich terminal display with live status updates and cost summary tables
- Permission system: allow/deny lists with glob patterns, `on_unmatched` policy, interactive `ask_via_stdin`

### Built-in nodes

- **Workflow:** `git_new_branch`, `git_commit`, `implement_feature`, `python_plan_feature`, `python_implement_feature`
- **Quality:** `code_review`, `security_audit`, `docs_review`, `python_test`, `python_coverage`, `python_dependency_audit`
- **Python tooling:** `python_lint` (ruff check), `python_format` (ruff format)
- **Resolution:** `resolve_findings` — interactive triage of upstream review findings

### Pre-built pipelines

- `codemonkeys python check` — lint → format → [test, review, security, docs, dep audit, type check] → resolve findings → lint

### Language skills

- Python, JavaScript, Rust clean-code and security guidance constants
