"""Main Textual application for codemonkeys."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.events import Click
from textual.widgets import Button, Footer, Header, Static

from codemonkeys.tui.screens.analyzer import AnalyzerScreen
from codemonkeys.tui.screens.dashboard import DashboardScreen
from codemonkeys.tui.screens.queue import QueueScreen
from codemonkeys.tui.theme import THEME_ORDER, THEMES


class Sidebar(Container):
    DEFAULT_CSS = """
    Sidebar {
        width: 28;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="logo")
        yield Static("")
        yield Button("  Home", id="nav-home", classes="nav-button -active")
        yield Button("  Analyze", id="nav-analyze", classes="nav-button")
        yield Button("  Queue", id="nav-queue", classes="nav-button")
        yield Button("  Dashboard", id="nav-dashboard", classes="nav-button")


class HomeContent(Container):
    def compose(self) -> ComposeResult:
        yield Static("", id="welcome-text", classes="welcome-panel")
        with Horizontal():
            with Container(classes="action-card", id="action-review"):
                yield Static("", id="review-title", classes="action-title")
                yield Static("", id="review-desc", classes="action-desc")
            with Container(classes="action-card", id="action-implement"):
                yield Static("", id="implement-title", classes="action-title")
                yield Static("", id="implement-desc", classes="action-desc")


class CodemonkeysApp(App[None]):
    TITLE = "codemonkeys"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("h", "go_home", "Home", show=True),
        Binding("a", "go_analyze", "Analyze", show=True),
        Binding("u", "go_queue", "Queue", show=True),
        Binding("d", "go_dashboard", "Dashboard", show=True),
        Binding("t", "cycle_theme", "Theme", show=True),
    ]

    def __init__(self, cwd: Path | None = None) -> None:
        self._theme_index = 0
        super().__init__()
        self.cwd = cwd or Path.cwd()
        self._current_view = "home"

    def get_css_variables(self) -> dict[str, str]:
        variables = super().get_css_variables()
        palette = THEMES[THEME_ORDER[self._theme_index]]
        variables.update(palette.to_variables())
        return variables

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield Sidebar()
            with Container(id="main-content"):
                yield HomeContent(id="view-home")
                yield AnalyzerScreen(id="view-analyze")
                yield DashboardScreen(id="view-dashboard")
                yield QueueScreen(id="view-queue")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#view-analyze").display = False
        self.query_one("#view-dashboard").display = False
        self.query_one("#view-queue").display = False
        self._update_theme_text()

    def _update_theme_text(self) -> None:
        palette = THEMES[THEME_ORDER[self._theme_index]]

        logo = self.query_one("#logo", Static)
        logo.update(f"  [bold {palette.accent}]codemonkeys[/]")

        welcome = self.query("#welcome-text")
        if welcome:
            welcome.first(Static).update(
                f"[bold {palette.accent}]codemonkeys[/]\n\n"
                f"[{palette.text_dim}]AI-powered code analysis and implementation workflows[/]"
            )

        for widget_id, text in [
            ("#review-title", "Run Code Review"),
            ("#implement-title", "Implement Feature"),
        ]:
            w = self.query(widget_id)
            if w:
                w.first(Static).update(f"[{palette.cyan} bold]{text}[/]")

        for widget_id, text in [
            ("#review-desc", "Analyze files for quality and security issues"),
            ("#implement-desc", "Plan and build a feature with TDD"),
        ]:
            w = self.query(widget_id)
            if w:
                w.first(Static).update(f"[{palette.text_dim}]{text}[/]")

        self.sub_title = palette.name

    def action_cycle_theme(self) -> None:
        self._theme_index = (self._theme_index + 1) % len(THEME_ORDER)
        self.refresh_css()
        self._update_theme_text()

    def action_go_home(self) -> None:
        self._switch_view("home")

    def action_go_analyze(self) -> None:
        self._switch_view("analyze")

    def action_go_queue(self) -> None:
        self._switch_view("queue")

    def action_go_dashboard(self) -> None:
        self._switch_view("dashboard")

    def _switch_view(self, view_id: str) -> None:
        for vid in ("home", "analyze", "dashboard", "queue"):
            widget = self.query_one(f"#view-{vid}")
            widget.display = vid == view_id

        for btn in self.query(".nav-button"):
            btn.remove_class("-active")
        self.query_one(f"#nav-{view_id}", Button).add_class("-active")
        self._current_view = view_id

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("nav-"):
            view = event.button.id.removeprefix("nav-")
            self._switch_view(view)

    def on_analyzer_screen_analysis_requested(
        self, event: AnalyzerScreen.AnalysisRequested
    ) -> None:
        self.notify(f"Reviewing {len(event.files)} file(s)...")
        self._switch_view("dashboard")
        self.run_worker(self._run_review(event.files), exclusive=True)

    async def _run_review(self, files: list[str]) -> None:
        import dataclasses
        import json
        import uuid
        from datetime import datetime, timezone

        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TaskNotificationMessage,
            TaskProgressMessage,
            TaskStartedMessage,
            ToolUseBlock,
            query,
        )

        from codemonkeys.artifacts.schemas.findings import FileFindings
        from codemonkeys.artifacts.store import ArtifactStore
        from codemonkeys.core.agents.python_file_reviewer import (
            make_python_file_reviewer,
        )

        dashboard = self.query_one("#view-dashboard", DashboardScreen)
        store = ArtifactStore(Path(self.cwd) / ".codemonkeys")
        run_id = store.new_run("review")
        log_dir = Path(self.cwd) / ".codemonkeys" / run_id
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "sdk_messages.jsonl"
        all_findings: list[FileFindings] = []

        def _serialize(obj: object) -> dict[str, object]:
            cls_name = type(obj).__name__
            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                fields = {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}
            else:
                fields = {
                    k: getattr(obj, k)
                    for k in dir(obj)
                    if not k.startswith("_") and not callable(getattr(obj, k, None))
                }
            safe: dict[str, object] = {}
            for k, v in fields.items():
                try:
                    json.dumps(v)
                    safe[k] = v
                except (TypeError, ValueError):
                    safe[k] = repr(v)
            return {"_class": cls_name, **safe}

        def _log(event: str, file: str, data: object) -> None:
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "file": file,
                "data": _serialize(data) if not isinstance(data, dict) else data,
            }
            with open(log_path, "a") as f:
                f.write(json.dumps(entry, default=repr) + "\n")

        for file_path in files:
            task_id = f"{file_path}-{uuid.uuid4().hex[:6]}"
            dashboard.add_agent(file_path, task_id)

            agent = make_python_file_reviewer([file_path])
            _log(
                "agent_definition",
                file_path,
                {
                    "_class": "AgentDefinition",
                    "description": agent.description,
                    "model": agent.model,
                    "tools": agent.tools,
                    "disallowedTools": agent.disallowedTools,
                    "skills": agent.skills,
                    "memory": agent.memory,
                    "mcpServers": agent.mcpServers,
                    "initialPrompt": agent.initialPrompt,
                    "maxTurns": agent.maxTurns,
                    "background": agent.background,
                    "effort": agent.effort,
                    "permissionMode": agent.permissionMode,
                    "prompt_length": len(agent.prompt),
                },
            )

            output_format = {
                "type": "json_schema",
                "schema": FileFindings.model_json_schema(),
            }
            options = ClaudeAgentOptions(
                system_prompt=agent.prompt,
                model=agent.model or "sonnet",
                cwd=str(self.cwd),
                permission_mode=agent.permissionMode or "dontAsk",
                allowed_tools=agent.tools or [],
                disallowed_tools=agent.disallowedTools or [],
                output_format=output_format,
            )
            _log("agent_options", file_path, _serialize(options))

            prompt = f"Review: {file_path}"
            tokens = 0
            tool_calls = 0
            result_text = ""
            last_result: ResultMessage | None = None

            async def _prompt_gen():
                yield {"type": "user", "message": {"role": "user", "content": prompt}}

            try:
                async for message in query(prompt=_prompt_gen(), options=options):
                    _log(type(message).__name__, file_path, message)

                    if isinstance(message, AssistantMessage):
                        usage = message.usage
                        if usage:
                            tokens = usage.get("total_tokens", 0) or (
                                usage.get("input_tokens", 0)
                                + usage.get("output_tokens", 0)
                            )
                        for block in message.content:
                            if isinstance(block, ToolUseBlock):
                                tool_calls += 1
                        dashboard.update_agent(task_id, tokens, tool_calls, "")

                    elif isinstance(message, TaskStartedMessage):
                        dashboard.update_agent(task_id, tokens, tool_calls, "started")

                    elif isinstance(message, TaskProgressMessage):
                        u = message.usage
                        if u:
                            tokens = u.get("total_tokens", 0)
                            tool_calls = u.get("tool_uses", 0)
                        tool_name = message.last_tool_name or ""
                        dashboard.update_agent(task_id, tokens, tool_calls, tool_name)

                    elif isinstance(message, TaskNotificationMessage):
                        u = message.usage
                        if u:
                            tokens = u.get("total_tokens", 0)

                    elif isinstance(message, ResultMessage):
                        result_text = getattr(message, "result", "") or ""
                        last_result = message
                        usage = message.usage
                        if usage:
                            tokens = usage.get("total_tokens", 0) or (
                                usage.get("input_tokens", 0)
                                + usage.get("output_tokens", 0)
                            )

                dashboard.complete_agent(task_id, tokens)

                structured = getattr(last_result, "structured_output", None)
                if structured:
                    if isinstance(structured, str):
                        structured = json.loads(structured)
                    findings = FileFindings.model_validate(structured)
                else:
                    try:
                        findings = FileFindings.model_validate_json(result_text)
                    except Exception:
                        findings = FileFindings(
                            file=file_path,
                            summary="Could not parse output",
                            findings=[],
                        )

                all_findings.append(findings)
                safe_name = file_path.replace("/", "__").replace("\\", "__")
                store.save(run_id, f"findings/{safe_name}", findings)

            except Exception as exc:
                _log("error", file_path, {"error": str(exc)})
                self.notify(f"Agent failed on {file_path}: {exc}", severity="error")
                dashboard.complete_agent(task_id, tokens)

        total = sum(len(f.findings) for f in all_findings)
        self.notify(f"Review complete: {total} finding(s) across {len(files)} file(s)")
        self.notify(f"SDK log: {log_path}")

    def on_click(self, event: Click) -> None:
        widget = event.widget
        while widget is not None:
            if widget.id == "action-review":
                self._switch_view("analyze")
                return
            if widget.id == "action-implement":
                self._switch_view("analyze")
                return
            widget = widget.parent
