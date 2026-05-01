"""Python coordinator — interactive session with constrained Python agents.

An interactive Claude session with deep Python expertise and specialized
agents for linting, testing, type checking, code review, security audit,
and implementation. You chat with the coordinator; it dispatches agents.

Usage:
    python -m codemonkeys.coordinators.python
    python -m codemonkeys.coordinators.python --cwd /path/to/project
"""

from __future__ import annotations

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions

from codemonkeys.prompts import ENGINEERING_MINDSET

from codemonkeys.agents import (
    make_changelog_reviewer,
    make_python_coverage_analyzer,
    make_python_dep_auditor,
    make_python_fixer,
    make_python_implementer,
    make_python_linter,
    make_python_quality_reviewer,
    make_readme_reviewer,
    make_python_security_auditor,
    make_python_test_runner,
    make_python_test_writer,
    make_python_type_checker,
)


def _python_agents() -> dict[str, AgentDefinition]:
    return {
        "python_linter": make_python_linter(),
        "python_type_checker": make_python_type_checker(),
        "python_test_runner": make_python_test_runner(),
        "python_coverage_analyzer": make_python_coverage_analyzer(),
        "python_dep_auditor": make_python_dep_auditor(),
        "python_test_writer": make_python_test_writer(),
        "python_quality_reviewer": make_python_quality_reviewer(),
        "python_security_auditor": make_python_security_auditor(),
        "readme_reviewer": make_readme_reviewer(),
        "changelog_reviewer": make_changelog_reviewer(),
        "python_fixer": make_python_fixer(),
        "python_implementer": make_python_implementer(),
    }

PYTHON_PROMPT = f"""\
You are an expert Python developer and technical lead. You have a team of
specialized agents you can dispatch for specific tasks. You read and
understand code yourself, but you NEVER edit files directly — all changes
go through your agents.

## Your Agents

### Reviewers (read-only — dispatch in parallel via multiple Agent calls in ONE response)

| Agent | What it reviews |
|-------|----------------|
| python_type_checker | Runs mypy, returns type errors |
| python_test_runner | Runs pytest, returns test failures |
| python_coverage_analyzer | Runs pytest --cov, returns uncovered lines |
| python_dep_auditor | Runs pip-audit, returns dependency vulnerabilities |
| python_quality_reviewer | Clean code review (naming, design, docstrings, patterns) |
| python_security_auditor | Security vulnerabilities (injection, secrets, auth) |
| readme_reviewer | README accuracy, completeness, stale references |
| changelog_reviewer | CHANGELOG.md completeness against git history |

### Writers (edit files — dispatch ONE at a time, wait for completion before next)

| Agent | What it does |
|-------|-------------|
| python_linter | Runs ruff check --fix + ruff format (auto-fix) |
| python_fixer | Fixes specific findings from reviewers |
| python_test_writer | Writes tests for uncovered code |
| python_implementer | Implements features, updates, bug fixes from a plan |

### Agent Output

Subagent responses land in your context window. To avoid overload:
- When dispatching a reviewer, tell it to cap output to the top 20
  findings max, prioritized by severity. If there are more, it should
  say "N additional low-severity findings omitted."
- When presenting findings to the user, summarize each reviewer's
  results in 2-3 sentences, then list individual findings. Do not
  dump raw agent output.

## Core Principle

ALWAYS tell the user what you're going to do before you do it. Present
your plan, wait for approval, then execute. Never dispatch agents
without the user knowing what's about to happen and agreeing to it.

The pattern for EVERY task:
1. **Understand**: Read code, gather context.
2. **Plan**: Tell the user exactly which agents you'll dispatch and why.
3. **Confirm**: Wait for the user to approve, adjust, or cancel.
4. **Execute**: Dispatch agents as planned.
5. **Report**: Present results and ask about next steps.

## Verify-Fix Loop

After any write agent edits code, verify with the deterministic agents
(python_linter, python_type_checker, python_test_runner). If
verification fails, dispatch python_fixer and verify again.

**Maximum 2 verify-fix cycles.** If issues remain after 2 cycles,
stop and report what's still failing — do NOT keep looping. The user
will decide how to proceed.

Never re-run review agents (quality_reviewer, security_auditor,
readme_reviewer, changelog_reviewer) as part of the verify-fix loop.
Those are expensive and non-deterministic — they run once during the
review phase only. Re-running them risks infinite loops where the
fixer and reviewer disagree.

## Workflows

When the user picks a workflow (by number, name, or natural language),
follow EVERY step in order. Do NOT skip steps. Do NOT combine steps.
Each numbered step is a separate action — complete it fully before
moving to the next one.

### 1. Full Review

Trigger: user says "full review", "quality check", "review everything",
"check my code", or picks option 1.

1. **Ask scope**: "What should I review?"
   - **This branch** (changes vs main) — you will pass scope="diff"
     to agents that support it
   - **Entire repo** — you will pass scope="repo"
   - **Specific files** — ask which files, pass scope="file" with path
   Wait for the user to answer before proceeding.
2. **Ask exclusions**: "I'll run all 8 reviewers (type checker, test
   runner, coverage, dep audit, quality, security, readme, changelog).
   Want to skip any?" Wait for answer.
3. **Dispatch reviewers**: Dispatch ALL of the following agents in a
   SINGLE response using multiple Agent tool calls — do NOT dispatch
   them one at a time, they are safe to run in parallel. Pass the
   scope the user chose to agents that accept it.
   Agents: python_type_checker, python_test_runner,
   python_coverage_analyzer, python_dep_auditor,
   python_quality_reviewer, python_security_auditor,
   readme_reviewer, changelog_reviewer.
4. **Report**: Present ALL findings grouped by reviewer. Include counts:
   "N findings total (X high, Y medium, Z low)."
5. **Triage**: Ask the user: "Which findings should I fix? You can say
   'all', 'high only', list specific ones, or 'none'." Wait for answer.
6. **Fix**: Dispatch "python_fixer" with the approved findings. If
   coverage gaps were flagged AND the user approved fixing them,
   dispatch "python_test_writer" after the fixer completes.
7. **Verify**: Run the verify-fix loop (max 2 cycles). Report final
   status: what was fixed, what still fails, what was skipped.

### 2. Implement a Feature

Trigger: user says "implement", "build", "add a feature", "create",
or picks option 2.

1. **Understand**: Ask the user to describe the feature. Then read the
   relevant code yourself (using Read, Glob, Grep). Understand the
   architecture and existing patterns. Read
   `docs/codemonkeys/architecture.md` if it exists.
2. **Plan**: Design the implementation. Be specific — list every file
   to create or modify, describe each change, explain how it fits the
   existing code. Present the full plan to the user.
3. **Confirm**: Ask "Does this plan look right? Any changes?" Wait for
   explicit approval. Do NOT proceed until they say yes.
4. **Execute**: Dispatch "python_implementer" with the FULL plan text
   (not a summary — the complete plan with all details).
5. **Verify**: Run the verify-fix loop (max 2 cycles). Report final
   status: files created/modified, tests pass/fail.

### 3. Fix a Bug

Trigger: user says "fix", "debug", "there's a bug", "this is broken",
or picks option 3.

1. **Understand**: Ask the user to describe the bug (what happens vs
   what should happen). Read the relevant code yourself to understand
   the root cause.
2. **Diagnose**: Tell the user what you think the root cause is and
   describe the fix you'd make. Be specific — name the file, the
   function, and the change.
3. **Confirm**: Ask "Should I fix this?" Wait for approval.
4. **Execute**: Dispatch "python_fixer" for targeted fixes. If the fix
   is complex (multiple files, architectural change), dispatch
   "python_implementer" with a full plan instead.
5. **Verify**: Run the verify-fix loop (max 2 cycles). Report final
   status.

### 4. Write Tests

Trigger: user says "write tests", "add tests", "improve coverage",
or picks option 4.

1. **Run coverage**: Tell the user you'll run coverage analysis first.
   Dispatch "python_coverage_analyzer".
2. **Report**: Present the uncovered files and line ranges. Show the
   overall coverage percentage.
3. **Confirm**: Ask "Want me to write tests for all uncovered areas,
   or specific files only?" Wait for answer.
4. **Execute**: Dispatch "python_test_writer" with the coverage report
   (filtered to the user's selection if they picked specific files).
5. **Verify**: Run the verify-fix loop (max 2 cycles). Report final
   status: tests written, coverage improvement.

### 5. Lint & Format

Trigger: user says "lint", "format", "clean up style", "ruff",
or picks option 5.

1. **Ask scope**: "What should I lint?"
   - **This branch** (changed files only)
   - **Entire repo**
   - **Specific file** — ask which file
   Wait for answer.
2. **Execute**: Dispatch "python_linter" with the chosen scope.
3. **Report**: Present what changed. No verify-fix loop needed — ruff
   is deterministic.

### 6. Freestyle

Trigger: user asks a question, wants to explore code, or anything
that doesn't match workflows 1-5.

No fixed steps. Read code, answer questions, explain architecture.
If the conversation leads to a task that matches a workflow above,
switch to that workflow.

## Rules

- NEVER edit files directly. Always dispatch an agent.
- Read code yourself for understanding. Dispatch agents for action.
- Only read files inside the working directory. Never access files
  outside the project.
- When presenting findings or plans, be clear and actionable.
- Reviewers are read-only and safe to dispatch in parallel. Writers
  edit files and must run one at a time, sequentially.
- NEVER exceed 2 verify-fix cycles. Report remaining issues to the
  user instead of continuing to loop.
- If an agent fails or returns an error, tell the user what happened
  and suggest next steps.
- Match your communication style to the user — be concise if they're
  concise, detailed if they ask for detail.
- At the start of every session, read `docs/codemonkeys/architecture.md`
  for project context (if it exists).

{ENGINEERING_MINDSET}"""

PYTHON_TOOLS = ["Read", "Glob", "Grep", "Agent"]


def python_coordinator(cwd: str = ".") -> ClaudeAgentOptions:
    """Create a Python coordinator configured for interactive use."""
    return ClaudeAgentOptions(
        system_prompt=PYTHON_PROMPT,
        model="sonnet",
        cwd=cwd,
        permission_mode="acceptEdits",
        allowed_tools=PYTHON_TOOLS,
        agents=_python_agents(),
    )


if __name__ == "__main__":
    import argparse
    import asyncio
    import logging
    import os
    import re
    import signal
    import subprocess
    import termios
    import time
    import sys
    from pathlib import Path

    from rich.console import Console

    from codemonkeys.agents import make_project_memory_agent
    from codemonkeys.runner import AgentRunner

    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeSDKClient,
        ResultMessage,
        TaskNotificationMessage,
        TaskProgressMessage,
        TaskStartedMessage,
        TextBlock,
        ToolUseBlock,
    )
    from prompt_toolkit.application import Application, get_app
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.document import Document
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import (
        BufferControl,
        ConditionalContainer,
        FormattedTextControl,
        HSplit,
        Layout,
        Window,
    )
    from prompt_toolkit.layout.dimension import Dimension
    from prompt_toolkit.layout.processors import BeforeInput
    from prompt_toolkit.lexers import Lexer
    from prompt_toolkit.styles import Style as PTStyle, merge_styles
    from prompt_toolkit.styles.pygments import style_from_pygments_cls

    import pygments.lexers
    from pygments.styles.monokai import MonokaiStyle
    from prompt_toolkit.output.vt100 import Vt100_Output

    from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
    from prompt_toolkit.selection import SelectionType

    # Enable button tracking (press/release/scroll) + button-event tracking
    # (drag motion while button held) + SGR encoding. Omit \x1b[?1003h
    # (any-event / hover tracking) — we only need drag, not idle motion.
    def _patched_enable_mouse(self: Vt100_Output) -> None:
        self.write_raw("\x1b[?1000h")
        self.write_raw("\x1b[?1002h")
        self.write_raw("\x1b[?1006h")

    def _patched_disable_mouse(self: Vt100_Output) -> None:
        self.write_raw("\x1b[?1000l")
        self.write_raw("\x1b[?1002l")
        self.write_raw("\x1b[?1006l")

    Vt100_Output.enable_mouse_support = _patched_enable_mouse  # type: ignore[assignment]
    Vt100_Output.disable_mouse_support = _patched_disable_mouse  # type: ignore[assignment]

    class _SelectableOutput(BufferControl):
        """BufferControl that supports click-drag text selection and scroll."""

        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)  # type: ignore[arg-type]
            self._last_click_time: float = 0.0
            self._selecting = False
            self.window: Window | None = None

        def mouse_handler(self, mouse_event: MouseEvent) -> object:
            buffer = self.buffer
            position = mouse_event.position

            if mouse_event.event_type == MouseEventType.SCROLL_UP:
                if self.window:
                    for _ in range(3):
                        self.window._scroll_up()
                return None

            if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
                if self.window:
                    for _ in range(3):
                        self.window._scroll_down()
                return None

            if not self._last_get_processed_line:
                return NotImplemented

            processed_line = self._last_get_processed_line(position.y)
            xpos = processed_line.display_to_source(position.x)
            index = buffer.document.translate_row_col_to_index(
                position.y, xpos,
            )

            if mouse_event.event_type == MouseEventType.MOUSE_DOWN:
                buffer.exit_selection()
                buffer.cursor_position = index
                self._selecting = True
                return None

            if (
                mouse_event.event_type == MouseEventType.MOUSE_MOVE
                and mouse_event.button != MouseButton.NONE
                and self._selecting
            ):
                if (
                    buffer.selection_state is None
                    and abs(buffer.cursor_position - index) > 0
                ):
                    buffer.start_selection(
                        selection_type=SelectionType.CHARACTERS,
                    )
                buffer.cursor_position = index
                return None

            if mouse_event.event_type == MouseEventType.MOUSE_UP:
                self._selecting = False
                if abs(buffer.cursor_position - index) > 1:
                    if buffer.selection_state is None:
                        buffer.start_selection(
                            selection_type=SelectionType.CHARACTERS,
                        )
                    buffer.cursor_position = index
                    self._copy_selection_to_clipboard()

                now = time.time()
                if now - self._last_click_time < 0.3:
                    start, end = buffer.document.find_boundaries_of_current_word()
                    buffer.cursor_position += start
                    buffer.start_selection(
                        selection_type=SelectionType.CHARACTERS,
                    )
                    buffer.cursor_position += end - start
                    self._copy_selection_to_clipboard()
                self._last_click_time = now
                return None

            return NotImplemented

        def _copy_selection_to_clipboard(self) -> None:
            """Copy selected text to system clipboard via OSC 52."""
            import base64

            sel = self.buffer.document.selection_range()
            if sel:
                start, end = sel
                text = self.buffer.text[start:end]
                encoded = base64.b64encode(text.encode()).decode()
                try:
                    output = get_app().output
                    output.write_raw(f"\x1b]52;c;{encoded}\x07")
                    output.flush()
                except Exception:
                    pass

    _log_path = Path("/tmp/codemonkeys_debug.log")
    logging.basicConfig(
        filename=str(_log_path),
        level=logging.DEBUG,
        format="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )
    _log = logging.getLogger("coordinator")

    parser = argparse.ArgumentParser(description="Python coordinator — interactive session")
    parser.add_argument("--cwd", default=".", help="Working directory (default: cwd)")
    parser.add_argument("prompt", nargs="*", help="Initial prompt (optional, starts REPL if omitted)")
    args = parser.parse_args()

    _CODE_FENCE_RE = re.compile(r"^```(\w*)")
    _MD_INLINE_RE = re.compile(
        r"(\*\*\*(.+?)\*\*\*"     # ***bold italic***
        r"|\*\*(.+?)\*\*"         # **bold**
        r"|\*(.+?)\*"             # *italic*
        r"|`([^`]+)`)"            # `inline code`
    )
    _MD_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)")

    def _style_markdown_line(line: str) -> list[tuple[str, str]]:
        heading = _MD_HEADING_RE.match(line)
        if heading:
            return [("class:md.heading", heading.group(2))]

        frags: list[tuple[str, str]] = []
        last = 0
        for m in _MD_INLINE_RE.finditer(line):
            if m.start() > last:
                frags.append(("", line[last:m.start()]))
            if m.group(2) is not None:
                frags.append(("class:md.bold_italic", m.group(2)))
            elif m.group(3) is not None:
                frags.append(("class:md.bold", m.group(3)))
            elif m.group(4) is not None:
                frags.append(("class:md.italic", m.group(4)))
            elif m.group(5) is not None:
                frags.append(("class:md.code", m.group(5)))
            last = m.end()
        if last == 0:
            return [("", line)]
        if last < len(line):
            frags.append(("", line[last:]))
        return frags

    def _build_code_line_map(lines: tuple[str, ...]) -> dict[int, list[tuple[str, str]]]:
        """Pre-scan lines for fenced code blocks and tokenize with Pygments."""
        result: dict[int, list[tuple[str, str]]] = {}
        i = 0
        while i < len(lines):
            m = _CODE_FENCE_RE.match(lines[i])
            if not m:
                i += 1
                continue
            lang = m.group(1) or "text"
            result[i] = [("class:output.dim", lines[i])]
            code_start = i + 1
            code_end = code_start
            while code_end < len(lines) and not lines[code_end].startswith("```"):
                code_end += 1
            code_text = "\n".join(lines[code_start:code_end])
            try:
                lexer = pygments.lexers.get_lexer_by_name(lang)
            except pygments.lexers.ClassNotFound:
                lexer = pygments.lexers.get_lexer_by_name("text")
            tokens = list(lexer.get_tokens(code_text))
            cur_line = code_start
            cur_frags: list[tuple[str, str]] = []
            for tok_type, tok_value in tokens:
                style = "class:pygments." + ".".join(str(tok_type).split(".")).lower()
                parts = tok_value.split("\n")
                for j, part in enumerate(parts):
                    if part:
                        cur_frags.append((style, part))
                    if j < len(parts) - 1:
                        result[cur_line] = cur_frags
                        cur_line += 1
                        cur_frags = []
            if cur_frags:
                result[cur_line] = cur_frags
            if code_end < len(lines):
                result[code_end] = [("class:output.dim", lines[code_end])]
            i = code_end + 1
        return result

    _HUNK_RE = re.compile(r"^@@ .+ @@")

    def _detect_diff_zones(lines: tuple[str, ...]) -> set[int]:
        """Find line ranges that look like unified diff output (outside code fences)."""
        zones: set[int] = set()
        i = 0
        in_fence = False
        while i < len(lines):
            if _CODE_FENCE_RE.match(lines[i]):
                in_fence = not in_fence
                i += 1
                continue
            if in_fence:
                i += 1
                continue
            if lines[i].startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
                zones.add(i)
                zones.add(i + 1)
                j = i + 2
                while j < len(lines):
                    ln = lines[j]
                    if ln.startswith(("+", "-", " ")) or _HUNK_RE.match(ln) or ln == "":
                        zones.add(j)
                        j += 1
                    else:
                        break
                i = j
                continue
            if _HUNK_RE.match(lines[i]):
                zones.add(i)
                j = i + 1
                while j < len(lines):
                    ln = lines[j]
                    if ln.startswith(("+", "-", " ")) or ln == "":
                        zones.add(j)
                        j += 1
                    else:
                        break
                i = j
                continue
            i += 1
        return zones

    def _style_diff_line(line: str) -> list[tuple[str, str]]:
        if line.startswith("+++") or line.startswith("---"):
            return [("class:diff.header", line)]
        if _HUNK_RE.match(line):
            return [("class:diff.hunk", line)]
        if line.startswith("+"):
            return [("class:diff.add", line)]
        if line.startswith("-"):
            return [("class:diff.remove", line)]
        return [("class:diff.context", line)]

    class _OutputLexer(Lexer):
        def __init__(self, banner_lines: int = 0) -> None:
            self._banner_lines = banner_lines

        def lex_document(self, document: Document) -> object:
            lines = document.lines
            code_map = _build_code_line_map(lines)
            diff_zones = _detect_diff_zones(lines)
            bl = self._banner_lines

            def get_line(lineno: int) -> list[tuple[str, str]]:
                if lineno >= len(lines):
                    return [("", "")]
                if lineno in code_map:
                    return code_map[lineno]
                line = lines[lineno]
                if not line:
                    return [("", "")]
                if bl and lineno < bl:
                    if line.startswith("codemonkeys"):
                        return [("class:output.title", line)]
                    return [("class:output.dim", line)]
                if lineno in diff_zones:
                    return _style_diff_line(line)
                if line.startswith("> "):
                    return [("class:output.user", line)]
                if "↳" in line:
                    return [("class:output.agent", line)]
                return _style_markdown_line(line)

            return get_line

    _SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    async def _update_project_memory(cwd: Path) -> None:
        """Check project memory freshness and update if stale."""
        hash_file = cwd / "docs" / "codemonkeys" / ".memory-hash"
        current_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(cwd),
        ).decode().strip()

        if hash_file.exists():
            stored_hash = hash_file.read_text().strip()
            if stored_hash == current_head:
                return
            diff = subprocess.check_output(
                ["git", "diff", f"{stored_hash}..HEAD"], cwd=str(cwd),
            ).decode()
            agent = make_project_memory_agent(mode="incremental", diff_text=diff)
            prompt = "Update the project memory document based on the diff."
        else:
            agent = make_project_memory_agent(mode="full")
            prompt = "Build the project memory document from scratch."

        console = Console(stderr=True)
        console.print("[bold]Updating project memory...[/bold]")
        runner = AgentRunner(cwd=str(cwd))
        await runner.run_agent(agent, prompt)
        console.print("[bold green]Project memory updated.[/bold green]")

    async def _main() -> None:
        session_tokens = 0
        coordinator_tokens = 0
        agent_tokens_total = 0
        turn_agent_tokens = 0
        session_cost: float = 0.0
        streaming = False
        turn_start: float = 0.0
        last_elapsed: float = 0.0
        spinner_idx = 0
        stream_task: asyncio.Task[str | None] | None = None
        input_queue: asyncio.Queue[str] = asyncio.Queue()
        output_parts: list[str] = []
        agent_states: dict[str, dict[str, object]] = {}
        agent_table_visible = False

        output_buffer = Buffer(read_only=True)

        def _on_accept(buff: Buffer) -> bool:
            text = buff.text.strip()
            if text and not streaming:
                input_queue.put_nowait(text)
            return False

        input_buffer = Buffer(
            name="input",
            history=InMemoryHistory(),
            accept_handler=_on_accept,
        )

        def _append(text: str) -> None:
            old_len = len(output_buffer.text)
            at_end = output_buffer.cursor_position >= old_len - 1
            output_parts.append(text)
            full = "".join(output_parts)
            cursor = len(full) if at_end or old_len == 0 else output_buffer.cursor_position
            output_buffer.set_document(
                Document(full, cursor_position=cursor),
                bypass_readonly=True,
            )
            app.invalidate()

        def _separator() -> list[tuple[str, str]]:
            return [("class:separator", "─" * os.get_terminal_size().columns)]

        def _separator_top() -> list[tuple[str, str]]:
            cols = os.get_terminal_size().columns
            if streaming:
                char = _SPINNER[spinner_idx % len(_SPINNER)]
                label = f" {char} working... "
                side = (cols - len(label)) // 2
                return [
                    ("class:separator", "─" * side),
                    ("class:thinking", label),
                    ("class:separator", "─" * (cols - side - len(label))),
                ]
            return [("class:separator", "─" * cols)]

        def _format_elapsed(secs: float) -> str:
            if secs < 60:
                return f"{secs:.1f}s"
            m, s = divmod(int(secs), 60)
            return f"{m}m {s:02d}s"

        def _toolbar() -> list[tuple[str, str]]:
            if exit_pending and time.monotonic() - exit_pending < 2.0:
                return [("class:toolbar.exit", " Press Ctrl+C again to exit")]
            cwd = Path(args.cwd).resolve()
            if streaming:
                elapsed = time.monotonic() - turn_start
                time_str = f" | elapsed: {_format_elapsed(elapsed)}"
            elif last_elapsed > 0:
                time_str = f" | last turn: {_format_elapsed(last_elapsed)}"
            else:
                time_str = ""
            tokens_parts = f"tokens: {session_tokens:,}"
            if coordinator_tokens or agent_tokens_total:
                tokens_parts += f" (coordinator: {coordinator_tokens:,} | agents: {agent_tokens_total:,})"
            cost_str = f" | ${session_cost:.4f}" if session_cost else ""
            return [("class:toolbar", f" {cwd} | {tokens_parts}{cost_str}{time_str}")]

        def _input_prefix() -> list[tuple[str, str]]:
            return [("class:prompt", "> ")]

        kb = KeyBindings()

        @kb.add("enter")
        def _on_enter(event: object) -> None:
            if not streaming:
                event.current_buffer.validate_and_handle()  # type: ignore[union-attr]

        @kb.add("escape", "enter")
        def _on_alt_enter(event: object) -> None:
            event.current_buffer.insert_text("\n")  # type: ignore[union-attr]

        @kb.add("pageup")
        def _on_page_up(event: object) -> None:
            if output_window.render_info:
                for _ in range(output_window.render_info.window_height):
                    output_window._scroll_up()
                app.invalidate()

        @kb.add("pagedown")
        def _on_page_down(event: object) -> None:
            if output_window.render_info:
                for _ in range(output_window.render_info.window_height):
                    output_window._scroll_down()
                app.invalidate()

        @kb.add("escape")
        def _on_escape(event: object) -> None:
            if output_buffer.selection_state is not None:
                output_buffer.exit_selection()
                app.invalidate()
            elif streaming and stream_task is not None:
                stream_task.cancel()

        exit_pending: float = 0.0

        @kb.add("c-c", eager=True)
        def _on_ctrl_c(event: object) -> None:
            nonlocal exit_pending
            now = time.monotonic()
            if output_buffer.selection_state is not None:
                output_control._copy_selection_to_clipboard()
                output_buffer.exit_selection()
                app.invalidate()
            elif streaming and stream_task is not None:
                stream_task.cancel()
            elif input_buffer.text:
                input_buffer.reset()
            elif now - exit_pending < 2.0:
                app.exit()
            else:
                exit_pending = now
                app.invalidate()

                async def _clear_exit_hint() -> None:
                    await asyncio.sleep(2.0)
                    app.invalidate()

                asyncio.ensure_future(_clear_exit_hint())

        @kb.add("c-d", eager=True)
        def _on_exit(event: object) -> None:
            if not streaming:
                app.exit()

        _base_style = PTStyle.from_dict({
            "separator": "ansibrightblack",
            "prompt": "bold ansigreen",
            "thinking": "italic ansired",
            "toolbar": "ansibrightblack",
            "toolbar.exit": "ansired",
            "output.title": "bold ansicyan",
            "output.user": "bold ansigreen",
            "output.agent": "ansibrightblack",
            "output.dim": "ansibrightblack",
            "diff.add": "ansigreen",
            "diff.remove": "ansired",
            "diff.hunk": "ansicyan",
            "diff.header": "bold ansiwhite",
            "diff.context": "",
            "md.bold": "bold",
            "md.italic": "italic",
            "md.bold_italic": "bold italic",
            "md.heading": "bold ansicyan",
            "md.code": "ansiyellow",
            "selected": "reverse",
        })
        pt_style = merge_styles([
            _base_style,
            style_from_pygments_cls(MonokaiStyle),
        ])

        output_lexer = _OutputLexer()

        output_control = _SelectableOutput(
            buffer=output_buffer,
            lexer=output_lexer,
            focusable=False,
        )
        output_window = Window(
            content=output_control,
            wrap_lines=True,
            height=Dimension(weight=1),
        )
        output_control.window = output_window

        def _agent_table_content() -> list[tuple[str, str]]:
            if not agent_states or not agent_table_visible:
                return [("", "")]
            now = time.monotonic()
            name_w = max(len(str(s.get("name", ""))) for s in agent_states.values()) + 1
            name_w = max(name_w, 8)
            time_w = 6
            tok_w = 7
            cols = os.get_terminal_size().columns
            act_w = max(20, cols - name_w - time_w - tok_w - 5)

            def hl(l: str, m: str, r: str) -> str:
                return f"{l}{'─' * name_w}{m}{'─' * time_w}{m}{'─' * tok_w}{m}{'─' * act_w}{r}"

            lines = [
                hl("┌", "┬", "┐"),
                f"│{'Agent':^{name_w}}│{'Time':^{time_w}}│{'Tok':^{tok_w}}│{'Activity':^{act_w}}│",
                hl("├", "┼", "┤"),
            ]
            for s in agent_states.values():
                name = str(s.get("name", ""))
                tokens = int(s.get("tokens", 0))
                started = float(s.get("started", now))
                end_time = s.get("end_time")
                if end_time:
                    elapsed = _format_elapsed(float(end_time) - started)
                else:
                    elapsed = _format_elapsed(now - started)
                tok_str = f"{tokens // 1000}k" if tokens >= 1000 else str(tokens)
                status = str(s.get("status", "running"))
                tool = str(s.get("last_tool", ""))
                if status == "complete":
                    activity = "✓ done"
                elif tool:
                    sp = _SPINNER[spinner_idx % len(_SPINNER)]
                    activity = f"{sp} {tool}"
                    if len(activity) > act_w - 1:
                        activity = activity[:act_w - 2] + "…"
                else:
                    sp = _SPINNER[spinner_idx % len(_SPINNER)]
                    activity = f"{sp} starting..."
                lines.append(
                    f"│{name:<{name_w}}│{elapsed:>{time_w}}│{tok_str:>{tok_w}}│ {activity:<{act_w - 1}}│"
                )
            lines.append(hl("└", "┴", "┘"))
            return [("class:output.dim", "\n".join(lines))]

        from prompt_toolkit.filters import Condition

        @Condition
        def _agents_running() -> bool:
            return agent_table_visible and bool(agent_states)

        agent_table_window = Window(
            content=FormattedTextControl(_agent_table_content),
            dont_extend_height=True,
        )

        layout = Layout(
            HSplit([
                output_window,
                ConditionalContainer(agent_table_window, filter=_agents_running),
                Window(height=1, content=FormattedTextControl(_separator_top)),
                Window(
                    content=BufferControl(
                        buffer=input_buffer,
                        input_processors=[BeforeInput(_input_prefix)],
                    ),
                    wrap_lines=True,
                    height=Dimension(min=1, max=10),
                    dont_extend_height=True,
                ),
                Window(height=1, content=FormattedTextControl(_separator)),
                Window(height=1, content=FormattedTextControl(_toolbar)),
            ]),
            focused_element=input_buffer,
        )

        app: Application[None] = Application(
            layout=layout,
            key_bindings=kb,
            style=pt_style,
            full_screen=True,
            mouse_support=True,
        )

        def _summarize_tool(name: str, inp: dict[str, object]) -> str:
            """Format tool name + key argument for the agent table."""
            if name in ("Read", "Edit", "Write"):
                path = str(inp.get("file_path", ""))
                if path:
                    return f"{name}({path})"
            elif name == "Glob":
                return f"Glob({inp.get('pattern', '')})"
            elif name == "Grep":
                return f"Grep({inp.get('pattern', inp.get('query', ''))})"
            elif name == "Bash":
                cmd = str(inp.get("command", ""))
                if len(cmd) > 60:
                    cmd = cmd[:57] + "..."
                return f"Bash({cmd})"
            return name

        async def _stream(client: ClaudeSDKClient) -> str | None:
            nonlocal session_tokens, coordinator_tokens, agent_tokens_total
            nonlocal turn_agent_tokens, session_cost, last_elapsed
            nonlocal agent_table_visible
            result_text = None
            prev_was_assistant = False
            turn_agent_tokens = 0
            active_tasks: dict[str, str] = {}
            task_tokens: dict[str, int] = {}
            tool_use_to_task: dict[str, str] = {}
            pending_agent_dispatches: dict[str, str] = {}

            async for message in client.receive_response():
                _log.debug("msg=%s", type(message).__name__)
                if isinstance(message, AssistantMessage):
                    if message.parent_tool_use_id and message.parent_tool_use_id in tool_use_to_task:
                        task_id = tool_use_to_task[message.parent_tool_use_id]
                        for block in message.content:
                            if isinstance(block, ToolUseBlock) and task_id in agent_states:
                                agent_states[task_id]["last_tool"] = _summarize_tool(
                                    block.name, block.input,
                                )
                        app.invalidate()
                    elif not message.parent_tool_use_id:
                        if prev_was_assistant:
                            current = "".join(output_parts)
                            if current and not current.endswith("\n"):
                                _append("\n")
                        prev_was_assistant = True
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                _append(block.text)
                            elif isinstance(block, ToolUseBlock) and block.name == "Agent":
                                agent_key = str(
                                    block.input.get("subagent_type")
                                    or block.input.get("agent_name")
                                    or block.input.get("name")
                                    or "",
                                )
                                if agent_key:
                                    pending_agent_dispatches[block.id] = agent_key
                elif isinstance(message, TaskStartedMessage):
                    agent_name = pending_agent_dispatches.pop(
                        message.tool_use_id or "", "",
                    ) or message.description
                    if message.tool_use_id:
                        tool_use_to_task[message.tool_use_id] = message.task_id
                    active_tasks[message.task_id] = agent_name
                    task_tokens[message.task_id] = 0
                    agent_states[message.task_id] = {
                        "name": agent_name,
                        "tokens": 0,
                        "last_tool": "",
                        "status": "running",
                        "started": time.monotonic(),
                        "end_time": None,
                    }
                    agent_table_visible = True
                    app.invalidate()
                elif isinstance(message, TaskProgressMessage):
                    if message.usage:
                        current_total = message.usage.get("total_tokens", 0)
                        prev_total = task_tokens.get(message.task_id, 0)
                        delta = current_total - prev_total
                        if delta > 0:
                            task_tokens[message.task_id] = current_total
                            turn_agent_tokens += delta
                            agent_tokens_total += delta
                            session_tokens += delta
                        if message.task_id in agent_states:
                            agent_states[message.task_id]["tokens"] = current_total
                    if message.last_tool_name and message.task_id in agent_states:
                        current_tool = str(agent_states[message.task_id].get("last_tool", ""))
                        if not current_tool.startswith(message.last_tool_name):
                            agent_states[message.task_id]["last_tool"] = message.last_tool_name
                    app.invalidate()
                elif isinstance(message, TaskNotificationMessage):
                    active_tasks.pop(message.task_id, None)
                    _log.debug("TaskNotification task=%s usage=%s", message.task_id, message.usage)
                    if message.usage:
                        final_total = message.usage.get("total_tokens", 0)
                        prev_total = task_tokens.pop(message.task_id, 0)
                        delta = final_total - prev_total
                        if delta > 0:
                            turn_agent_tokens += delta
                            agent_tokens_total += delta
                            session_tokens += delta
                        if message.task_id in agent_states:
                            agent_states[message.task_id]["tokens"] = final_total
                    if message.task_id in agent_states:
                        agent_states[message.task_id]["status"] = "complete"
                        agent_states[message.task_id]["end_time"] = time.monotonic()
                    app.invalidate()
                    if not any(s.get("status") != "complete" for s in agent_states.values()):
                        agent_table_visible = False
                        agent_states.clear()
                elif isinstance(message, ResultMessage):
                    result_text = message.result or ""
                    _log.debug("ResultMessage.model_usage=%s", message.model_usage)
                    _log.debug("ResultMessage.total_cost_usd=%s", message.total_cost_usd)
                    if message.total_cost_usd:
                        session_cost = message.total_cost_usd
                    model_usage = message.model_usage or {}
                    total_all_models = sum(
                        m.get("inputTokens", 0) + m.get("outputTokens", 0)
                        + m.get("cacheReadInputTokens", 0)
                        + m.get("cacheCreationInputTokens", 0)
                        for m in model_usage.values()
                    )
                    coord_total = max(total_all_models - agent_tokens_total, 0)
                    if coord_total > coordinator_tokens:
                        coordinator_tokens = coord_total
                        session_tokens = coordinator_tokens + agent_tokens_total
                    last_elapsed = time.monotonic() - turn_start
                    app.invalidate()
            _append("\n\n")
            return result_text

        async def _refresh_ui() -> None:
            nonlocal spinner_idx
            while True:
                await asyncio.sleep(0.1)
                if streaming:
                    spinner_idx += 1
                    app.invalidate()

        async def _run_stream(client: ClaudeSDKClient) -> None:
            nonlocal stream_task, streaming
            stream_task = asyncio.create_task(_stream(client))
            try:
                await stream_task
            except asyncio.CancelledError:
                _append("\n[interrupted]\n")
            finally:
                stream_task = None
                streaming = False
                app.invalidate()

        async def _chat_loop() -> None:
            nonlocal streaming, turn_start

            options = python_coordinator(cwd=args.cwd)
            resolved_cwd = Path(options.cwd or ".").resolve()

            from codemonkeys.sandbox import restrict
            restrict(resolved_cwd)

            await _update_project_memory(resolved_cwd)

            banner_lines = [
                "codemonkeys — Python Coordinator",
                f"model: {options.model}  |  cwd: {resolved_cwd}",
                "",
                "  What would you like to do?",
                "",
                "  1. Full Review     — lint, type check, test, review quality & security, fix findings",
                "  2. Implement       — plan a feature, get approval, build it, verify",
                "  3. Fix             — diagnose and fix a bug or specific issue",
                "  4. Write Tests     — find uncovered code and write tests for it",
                "  5. Lint & Format   — auto-fix style issues with ruff",
                "  6. Freestyle       — ask questions, explore code, anything else",
                "",
                "  Or just describe what you need in plain language.",
                "",
            ]
            output_lexer._banner_lines = len(banner_lines)
            _append("\n".join(banner_lines) + "\n")

            client = ClaudeSDKClient(options)
            initial = " ".join(args.prompt) if args.prompt else None

            try:
                turn_start = time.monotonic()
                streaming = True
                app.invalidate()

                if initial:
                    await client.connect(initial)
                else:
                    await client.connect("Greet the user briefly. One sentence.")

                await _run_stream(client)

                while True:
                    user_input = await input_queue.get()
                    if user_input.lower() in ("exit", "quit", "q"):
                        app.exit()
                        return

                    _append(f"> {user_input}\n\n")

                    turn_start = time.monotonic()
                    streaming = True
                    app.invalidate()
                    await client.query(user_input)
                    await _run_stream(client)

            finally:
                await client.disconnect()

        async def _start_chat() -> None:
            await asyncio.sleep(0)
            try:
                await _chat_loop()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                _append(f"\nError: {exc}\n")

        chat_task = asyncio.create_task(_start_chat())
        refresh_task = asyncio.create_task(_refresh_ui())
        try:
            await app.run_async()
        finally:
            chat_task.cancel()
            refresh_task.cancel()
            for task in (chat_task, refresh_task):
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    signal.signal(signal.SIGINT, signal.SIG_IGN)
    saved_attrs = termios.tcgetattr(sys.stdin.fileno())
    try:
        asyncio.run(_main())
    finally:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, saved_attrs)
        print()
