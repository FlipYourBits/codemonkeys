from __future__ import annotations

from codemonkeys.core.agents.architecture_reviewer import make_architecture_reviewer


class TestArchitectureReviewer:
    def test_returns_agent_definition(self) -> None:
        file_summaries = [
            {"file": "src/a.py", "summary": "HTTP price fetcher"},
            {"file": "src/b.py", "summary": "WebSocket price feed"},
        ]
        files = ["src/a.py", "src/b.py"]
        agent = make_architecture_reviewer(files=files, file_summaries=file_summaries)
        assert agent.model == "opus"

    def test_prompt_contains_design_review_checklist(self) -> None:
        agent = make_architecture_reviewer(
            files=["a.py"],
            file_summaries=[{"file": "a.py", "summary": "test"}],
        )
        assert "paradigm_inconsistency" in agent.prompt
        assert "layer_violation" in agent.prompt
        assert "Design Review Checklist" in agent.prompt

    def test_prompt_contains_file_summaries(self) -> None:
        agent = make_architecture_reviewer(
            files=["src/a.py", "src/b.py"],
            file_summaries=[
                {"file": "src/a.py", "summary": "Price fetcher via HTTP"},
                {"file": "src/b.py", "summary": "Price feed via WebSocket"},
            ],
        )
        assert "src/a.py" in agent.prompt
        assert "Price fetcher via HTTP" in agent.prompt
        assert "src/b.py" in agent.prompt

    def test_prompt_contains_all_files_to_review(self) -> None:
        files = ["src/a.py", "src/b.py", "src/c.py"]
        agent = make_architecture_reviewer(
            files=files,
            file_summaries=[{"file": f, "summary": "test"} for f in files],
        )
        for f in files:
            assert f in agent.prompt

    def test_has_read_and_grep_tools(self) -> None:
        agent = make_architecture_reviewer(
            files=["a.py"],
            file_summaries=[{"file": "a.py", "summary": "test"}],
        )
        assert "Read" in agent.tools
        assert "Grep" in agent.tools

    def test_permission_mode_is_dont_ask(self) -> None:
        agent = make_architecture_reviewer(
            files=["a.py"],
            file_summaries=[{"file": "a.py", "summary": "test"}],
        )
        assert agent.permissionMode == "dontAsk"
