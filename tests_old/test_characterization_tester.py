from __future__ import annotations


class TestMakeCharacterizationTester:
    def test_creates_agent_definition(self) -> None:
        from codemonkeys.core.agents.python_characterization_tester import (
            make_python_characterization_tester,
        )

        agent = make_python_characterization_tester(
            files=["core/runner.py", "core/analysis.py"],
            import_context="core/runner.py imports: analysis, sandbox",
            uncovered_lines={
                "core/runner.py": [10, 20, 30],
                "core/analysis.py": [5, 15],
            },
        )
        assert agent.model == "sonnet"
        assert "Read" in agent.tools
        assert "Write" in agent.tools
        assert any("pytest" in t for t in agent.tools)
        assert "runner.py" in agent.prompt
        assert "analysis.py" in agent.prompt

    def test_prompt_includes_uncovered_lines(self) -> None:
        from codemonkeys.core.agents.python_characterization_tester import (
            make_python_characterization_tester,
        )

        agent = make_python_characterization_tester(
            files=["foo.py"],
            import_context="foo.py imports: bar",
            uncovered_lines={"foo.py": [42, 99]},
        )
        assert "42" in agent.prompt
        assert "99" in agent.prompt

    def test_permission_mode(self) -> None:
        from codemonkeys.core.agents.python_characterization_tester import (
            make_python_characterization_tester,
        )

        agent = make_python_characterization_tester(
            files=["x.py"],
            import_context="",
            uncovered_lines={},
        )
        assert agent.permissionMode == "acceptEdits"
