"""Characterization test writer — locks current behavior for uncovered files."""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition

from codemonkeys.core.prompts import PYTHON_CMD, PYTHON_GUIDELINES


def make_python_characterization_tester(
    files: list[str],
    import_context: str,
    uncovered_lines: dict[str, list[int]],
) -> AgentDefinition:
    file_list = "\n".join(f"- `{f}`" for f in files)

    uncovered_section = ""
    for f, lines in uncovered_lines.items():
        if lines:
            line_str = ", ".join(str(ln) for ln in lines[:50])
            uncovered_section += f"\n### `{f}` — uncovered lines: {line_str}\n"

    return AgentDefinition(
        description=f"Write characterization tests for {len(files)} file(s)",
        prompt=f"""\
You write characterization tests that lock the current behavior of existing code.
Your goal is to maximize line coverage for the files listed below.

## Environment

Run tests with: `{PYTHON_CMD} -m pytest <test_file> -v`

This is the only Bash command you are allowed to run. Do NOT:
- Install packages (pip install, uv add, etc.)
- Run git commands (git stash, git diff, etc.)
- Explore the environment (ls, find, which, etc.)
- Read pyproject.toml or configuration files
- Run any command other than pytest

All dependencies are already installed. The test runner works. Use it exactly as shown.

## Files to Test

{file_list}

## Import Context

{import_context}

## Uncovered Lines
{uncovered_section}

## Method

1. Read each source file to understand what it does.
2. Check if a test file already exists (e.g. `tests/test_<stem>.py`). If it does,
   add new tests to it rather than overwriting. If not, create a new test file.
3. Write tests that exercise the uncovered lines listed above.
4. Focus on testing observable behavior: return values, side effects, exceptions.
5. Run `{PYTHON_CMD} -m pytest <test_file> -v` to verify every test passes.
6. If a test fails, fix the TEST — never modify the source code.

## Rules

- Tests MUST pass. They characterize what the code does now, not what it should do.
- Do not modify source files under any circumstances.
- Do not modify `conftest.py` files.
- Do not add type stubs or fixtures unless necessary for import.
- Prefer simple, direct tests over elaborate fixtures.
- Prefer Edit over Write when adding tests to an existing file.
- Use `unittest.mock.patch` sparingly — only when the code has side effects
  (file I/O, network, subprocess) that cannot be avoided.
- Name tests descriptively: `test_<function>_<scenario>`.
- Maximum 2 test-fix cycles per file. If tests still fail, skip the file and
  note why in your output.

{PYTHON_GUIDELINES}""",
        model="sonnet",
        tools=[
            "Read",
            "Edit",
            "Write",
            "Glob",
            "Grep",
            f"Bash({PYTHON_CMD} -m pytest*)",
        ],
        permissionMode="acceptEdits",
    )
