from __future__ import annotations


class TestMakeStructuralRefactorer:
    def test_creates_agent_definition(self) -> None:
        from codemonkeys.core.agents.python_structural_refactorer import (
            make_python_structural_refactorer,
        )

        agent = make_python_structural_refactorer(
            files=["a.py", "b.py"],
            problem_description="Circular dependency: a.py -> b.py -> a.py",
            refactor_type="circular_deps",
            test_files=["tests/test_a.py"],
        )
        assert agent.model == "sonnet"
        assert "Edit" in agent.tools
        assert "Write" in agent.tools
        assert any("pytest" in t for t in agent.tools)
        assert any("ruff" in t for t in agent.tools)
        assert "a.py" in agent.prompt
        assert "Circular dependency" in agent.prompt

    def test_includes_scoped_test_command(self) -> None:
        from codemonkeys.core.agents.python_structural_refactorer import (
            make_python_structural_refactorer,
        )

        agent = make_python_structural_refactorer(
            files=["core/runner.py"],
            problem_description="God module: 500 lines, 15 functions",
            refactor_type="god_modules",
            test_files=["tests/test_runner.py"],
        )
        assert "tests/test_runner.py" in agent.prompt

    def test_all_refactor_types(self) -> None:
        from codemonkeys.core.agents.python_structural_refactorer import (
            REFACTOR_INSTRUCTIONS,
            make_python_structural_refactorer,
        )

        for refactor_type in REFACTOR_INSTRUCTIONS:
            agent = make_python_structural_refactorer(
                files=["x.py"],
                problem_description="test",
                refactor_type=refactor_type,
                test_files=[],
            )
            assert agent.model == "sonnet"
