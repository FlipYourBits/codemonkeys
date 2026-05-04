# codemonkeys

Skill-driven workflows for Python development in [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Provides structured code review, feature implementation with TDD, and architecture documentation — all as Claude Code skills.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- Python 3.10+

### Optional Tool Dependencies

Skills run these tools as part of their workflows. Missing tools are skipped gracefully:

| Tool | Used by | Install |
|------|---------|---------|
| ruff | python-review, python-feature | `pip install ruff` |
| pyright | python-review | `pip install pyright` |
| pytest | python-review, python-feature | `pip install pytest` |
| pip-audit | python-review | `pip install pip-audit` |

To install everything:

```bash
pip install ruff pyright pytest pip-audit
```

## Installation

1. Copy the `codemonkeys` directory into your project's `.claude/` directory:

```bash
cp -r path/to/codemonkeys .claude/codemonkeys
```

2. Add the plugin reference to `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "local": {
      "source": { "source": "directory", "path": "./.claude/codemonkeys" }
    }
  },
  "enabledPlugins": {
    "codemonkeys@local": true
  }
}
```

If you already have a `.claude/settings.json`, merge these two keys into it.

3. Start Claude Code and run `/codemonkeys:python-feature` to get started.

## Uninstall

1. Delete `.claude/codemonkeys/`
2. Remove `codemonkeys@local` from `enabledPlugins` and `local` from `extraKnownMarketplaces` in `.claude/settings.json`

## Skills

### python-feature

Design-to-implementation workflow for new Python features.

```
/codemonkeys:python-feature
```

Walks through clarifying questions, design approaches, and a plan document. Once the plan is approved, dispatches the `python-implementer` agent to implement with TDD, then verifies with ruff, pyright, and pytest.

### python-review

Full Python code review with mechanical checks and manual review checklists.

```
/codemonkeys:python-review
```

Runs up to 9 review categories: quality, security, type checking (pyright), tests (pytest), coverage, linting (ruff), dependency audit (pip-audit), changelog review, and README review. Presents findings with severity and recommendations, then fixes approved issues.

### project-architecture

Builds and maintains a `docs/architecture.md` file — a comprehensive snapshot of the project.

```
/codemonkeys:project-architecture
```

Tracks freshness via a commit hash. On first run it documents the full project; on subsequent runs it incrementally updates only what changed.

## Agent

### python-implementer

Implements features, updates, and bug fixes from an approved plan file using TDD. Dispatched by the `python-feature` skill — not invoked directly. Reads the plan, writes failing tests first, then implements the code to make them pass.

## License

[MIT](LICENSE)
