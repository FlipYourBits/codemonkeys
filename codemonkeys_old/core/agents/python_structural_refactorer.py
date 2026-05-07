"""Structural refactorer — executes scoped structural changes guided by StructuralReport."""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.core.prompts import ENGINEERING_MINDSET, PYTHON_CMD, PYTHON_GUIDELINES

REFACTOR_INSTRUCTIONS: dict[str, str] = {
    "circular_deps": """\
Break the circular dependency described below. Common strategies:
- Extract shared types/interfaces into a third module both can import.
- Invert the dependency direction using dependency injection.
- Merge the modules if they are conceptually one unit.
- Use late imports (inside functions) only as a last resort.""",
    "layering": """\
Fix the layer violation described below. The import crosses a boundary
that should be respected. Move the shared code to the appropriate layer,
or restructure so the lower layer doesn't depend on the higher one.""",
    "god_modules": """\
Split the oversized module into focused, single-responsibility modules.
- Identify cohesive groups of functions/classes that work together.
- Extract each group into its own module.
- Update imports across the codebase to point to the new locations.
- The original module can re-export for backwards compatibility if needed.""",
    "extract_shared": """\
Extract duplicated code into a shared module.
- Identify the common pattern across the duplicate sites.
- Create a single implementation in an appropriate shared location.
- Replace all duplicate sites with calls to the shared code.
- Ensure the shared interface is clean and well-named.""",
    "dead_code": """\
Remove the dead code identified below. Verify it is truly unreachable:
- Check for dynamic references (getattr, importlib, string-based dispatch).
- Check for use in tests, scripts, or CLI entry points.
- If truly dead, delete it cleanly with no stubs or comments.""",
    "naming": """\
Rename the inconsistent identifiers below to match the codebase convention.
- Update ALL references across the codebase (imports, calls, strings).
- Use your editor tools to find all occurrences before renaming.
- Verify no references are missed after renaming.""",
}


def make_python_structural_refactorer(
    files: list[str],
    problem_description: str,
    refactor_type: str,
    test_files: list[str],
) -> AgentDefinition:
    file_list = "\n".join(f"- `{f}`" for f in files)
    instructions = REFACTOR_INSTRUCTIONS.get(
        refactor_type, "Follow the problem description below."
    )

    test_cmd = f"{PYTHON_CMD} -m pytest -x -q --tb=short --no-header"
    if test_files:
        test_cmd += " " + " ".join(test_files)

    return AgentDefinition(
        description=f"Refactor ({refactor_type}): {', '.join(files)}",
        prompt=f"""\
You are a structural refactoring agent. You make targeted structural changes
to improve codebase organization. You only touch the files listed below.

## Environment

Run tests with: `{test_cmd}`
Run lint with: `{PYTHON_CMD} -m ruff check --fix .` and `{PYTHON_CMD} -m ruff format .`

These are the only Bash commands you are allowed to run. Do NOT:
- Install packages (pip install, uv add, etc.)
- Run git commands (git stash, git diff, git commit, etc.)
- Explore the environment (ls, find, which, etc.)
- Run any command other than pytest and ruff

All dependencies are already installed. The test runner and linter work. Use them exactly as shown.

## Refactor Type: {refactor_type}

{instructions}

## Problem

{problem_description}

## Files You May Modify

{file_list}

## Scoped Test Command

After making changes, run:
```
{test_cmd}
```

## Method

1. Read all listed files to understand the current structure.
2. Plan the minimal structural change that solves the problem.
3. Make the changes.
4. Run `{PYTHON_CMD} -m ruff check --fix .` and `{PYTHON_CMD} -m ruff format .`
5. Run the scoped test command above.
6. If tests fail, fix the issue. Maximum 2 fix cycles.

## Rules

- Only touch files listed above. If you need to create a new file to
  extract code into, that's allowed.
- For naming refactors, use Glob and Grep to find ALL references across the
  codebase before renaming. Update every reference.
- Prefer Edit over Write — only use Write for new files.
- Make the minimal change. Don't improve code style, add features, or
  refactor beyond the stated problem.
- Preserve all public interfaces unless the problem requires changing them.
- Do not commit, push, or modify git state.

{ENGINEERING_MINDSET}

{PYTHON_GUIDELINES}""",
        model="sonnet",
        tools=[
            "Read",
            "Glob",
            "Grep",
            "Edit",
            "Write",
            f"Bash({PYTHON_CMD} -m pytest*)",
            f"Bash({PYTHON_CMD} -m ruff*)",
        ],
        permissionMode="acceptEdits",
    )
