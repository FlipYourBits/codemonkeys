# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Interactive Python coordinator TUI with prompt-toolkit — chat with a coordinator that dispatches constrained subagents (`codemonkeys.coordinators.python`)
- `make_python_implementer()` agent for implementing features from approved plans
- `make_python_coverage_analyzer()` agent for generating pytest coverage reports (pairs with test_writer)
- `make_python_changelog_writer()` agent for writing keepachangelog entries from git history
- `AgentRunner` for running individual agents with a Rich live display
- Composable coordinator architecture — coordinators extend base coordinators with additional agents and prompt
- Reusable prompt fragments in `codemonkeys/prompts/` (`PYTHON_GUIDELINES`, `PYTHON_SOURCE_FILTER`, `PYTHON_CMD`)
- Error handling instructions and single-turn constraints to all mechanical agents (linter, type_checker, test_runner, dep_auditor)
- Structured output format specs for write agents (fixer, implementer, test_writer)
- Finding caps (15) for all review agents (code_reviewer, security_auditor, docs_reviewer)
- Test failure handling with retry caps for all write agents

### Changed

- **Breaking:** renamed package from `agentpipe` to `codemonkeys`
- **Breaking:** replaced pipeline/node architecture with agent/coordinator architecture
- Agents are now `AgentDefinition` factory functions (`make_python_*()`) instead of constants, enabling parameterization (e.g., `make_python_quality_reviewer(scope="repo")`)
- Coordinator dispatches agents via Claude Agent SDK `ClaudeSDKClient` instead of custom pipeline orchestrator
- Agent table in TUI shows registered agent names (e.g., "code_reviewer") instead of generic "local_agent"
- Agent table moved to separate `ConditionalContainer` to prevent scroll locking during agent dispatch

### Removed

- `agentpipe` package (replaced by `codemonkeys`)
- Pipeline/node orchestrator (`Pipeline`, `ClaudeAgentNode`, `ShellNode`)
- Skills system (`agentpipe.skills`)
- Node-level `reads_from` / budget / permission system (replaced by SDK-native features)
- `resolve_findings` interactive triage node (replaced by coordinator conversation flow)

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
