# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Interactive Python coordinator TUI with prompt-toolkit — chat with a coordinator that dispatches constrained subagents (`codemonkeys.coordinators.python`)
- `make_python_implementer()` agent for implementing features from approved plans
- `make_python_coverage_analyzer()` agent for generating pytest coverage reports (pairs with test_writer)
- `make_changelog_reviewer()` agent for reviewing CHANGELOG.md against git history
- `AgentRunner` for running individual agents with a Rich live display
- Composable coordinator architecture — coordinators extend base coordinators with additional agents and prompt
- Reusable prompt fragments in `codemonkeys/prompts/` (`PYTHON_GUIDELINES`, `PYTHON_SOURCE_FILTER`, `PYTHON_CMD`)
- Error handling instructions and single-turn constraints to all mechanical agents (linter, type_checker, test_runner, dep_auditor)
- Structured output format specs for write agents (fixer, implementer, test_writer)
- Finding caps (15) for all review agents (code_reviewer, security_auditor, docs_reviewer)
- Test failure handling with retry caps for all write agents
- `make_project_memory_agent()` and `make_project_memory_updater()` agents for building and maintaining `docs/codemonkeys/architecture.md` — full-scan on first run, incremental diff-based updates on subsequent runs
- `--use-project-memory` flag on the Python coordinator to auto-update project memory before each session
- `make_definition_reviewer()` agent for reviewing `AgentDefinition` files for prompt quality, permission correctness, and model selection
- OS-level filesystem sandbox (`codemonkeys.sandbox.restrict()`) that restricts agent write access to the project directory — Linux via Landlock LSM, macOS via sandbox-exec/Seatbelt, Windows via Low Integrity Token
- `ENGINEERING_MINDSET` prompt fragment — engineering principles injected into the Python coordinator system prompt
- Output schema constants in `codemonkeys.schemas` (`REVIEW_RESULT_SCHEMA`, `TOOL_RESULT_SCHEMA`, `WRITER_RESULT_SCHEMA`, `FIX_RESULT_SCHEMA`) for structured output when running agents standalone
- `run_cli()` helper in `codemonkeys.runner` for running agents from command-line entry points (`python -m codemonkeys.agents.*`)
- `make_readme_reviewer()` agent for reviewing README accuracy, completeness, and quality against the actual codebase
- `make_python_fixer()` agent for applying targeted fixes identified by review agents
- `make_python_test_writer()` agent for writing pytest tests for uncovered code, driven by coverage analysis output
- `AppShell` in `codemonkeys.shell` — reusable full-screen TUI shell for building interactive coordinators

### Changed

- **Breaking:** renamed package from `agentpipe` to `codemonkeys`
- **Breaking:** replaced pipeline/node architecture with agent/coordinator architecture
- Agents are now `AgentDefinition` factory functions (`make_python_*()`) instead of constants, enabling parameterization (e.g., `make_python_quality_reviewer(scope="repo")`)
- Coordinator dispatches agents via Claude Agent SDK `ClaudeSDKClient` instead of custom pipeline orchestrator
- Agent table in TUI shows registered agent names (e.g., "code_reviewer") instead of generic "local_agent"
- Agent table moved to separate `ConditionalContainer` to prevent scroll locking during agent dispatch
- Coordinator TUI startup replaced generic agent table with a numbered workflow menu (Full Review, Implement, Fix a Bug, Write Tests, Lint & Format, Freestyle) with explicit step-by-step instructions for each workflow
- Coordinator now instructs reviewers to cap output at 20 findings per run, prioritized by severity
- Mechanical agent factories now importable standalone: `make_python_linter()`, `make_python_type_checker()`, `make_python_test_runner()`, `make_python_dep_auditor()`

### Fixed

- Coordinator `--use-project-memory` no longer crashes when run outside a git repository — project memory update is silently skipped

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
- Built-in workflow nodes: `git_new_branch`, `git_commit`, `implement_feature`, `python_plan_feature`, `python_implement_feature`
- Built-in quality nodes: `code_review`, `security_audit`, `docs_review`, `python_test`, `python_coverage`, `python_dependency_audit`
- Built-in Python tooling nodes: `python_lint` (ruff check), `python_format` (ruff format)
- Built-in resolution node: `resolve_findings` — interactive triage of upstream review findings
- Pre-built pipeline `codemonkeys python check` — lint → format → [test, review, security, docs, dep audit, type check] → resolve findings → lint
- Language skills — Python, JavaScript, Rust clean-code and security guidance constants
