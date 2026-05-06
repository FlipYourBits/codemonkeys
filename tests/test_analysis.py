from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from codemonkeys.core.analysis import (
    FileAnalysis,
    analyze_file,
    analyze_files,
    format_analysis,
)

ROOT = Path(__file__).resolve().parent.parent


class TestAnalyzeFile:
    def test_extracts_imports(self) -> None:
        result = analyze_file("codemonkeys/core/runner.py", root=ROOT)
        modules = [i["module"] for i in result.imports]
        assert "claude_agent_sdk" in modules
        assert "codemonkeys.core.run_result" in modules

    def test_extracts_top_level_functions(self) -> None:
        result = analyze_file("codemonkeys/workflows/compositions.py", root=ROOT)
        names = [f.name for f in result.functions]
        assert "make_files_workflow" in names
        assert "make_diff_workflow" in names

    def test_detects_async_functions(self) -> None:
        result = analyze_file("codemonkeys/workflows/phase_library/review.py", root=ROOT)
        by_name = {f.name: f for f in result.functions}
        assert by_name["file_review"].is_async is True
        assert by_name["_extract_hunks_for_files"].is_async is False

    def test_extracts_return_types(self) -> None:
        result = analyze_file("codemonkeys/workflows/compositions.py", root=ROOT)
        by_name = {f.name: f for f in result.functions}
        assert by_name["make_files_workflow"].return_type == "Workflow"

    def test_extracts_classes_and_methods(self) -> None:
        result = analyze_file("codemonkeys/core/runner.py", root=ROOT)
        class_names = [c.name for c in result.classes]
        assert "AgentRunner" in class_names
        runner = next(c for c in result.classes if c.name == "AgentRunner")
        method_names = [m.name for m in runner.methods]
        assert "run_agent" in method_names
        assert "_emit" in method_names

    def test_extracts_class_bases(self) -> None:
        result = analyze_file("codemonkeys/artifacts/schemas/findings.py", root=ROOT)
        class_names = [c.name for c in result.classes]
        assert "Finding" in class_names
        finding = next(c for c in result.classes if c.name == "Finding")
        assert "BaseModel" in finding.bases

    def test_extracts_decorators(self, tmp_path: Path) -> None:
        code = dedent("""\
            def plain(): ...

            def retry(f): return f

            @retry
            def decorated(): ...
        """)
        (tmp_path / "deco.py").write_text(code)
        result = analyze_file("deco.py", root=tmp_path)
        by_name = {f.name: f for f in result.functions}
        assert by_name["plain"].decorators == []
        assert by_name["decorated"].decorators == ["retry"]

    def test_handles_syntax_error(self, tmp_path: Path) -> None:
        (tmp_path / "bad.py").write_text("def broken(")
        result = analyze_file("bad.py", root=tmp_path)
        assert result.error is not None
        assert result.imports == []

    def test_handles_missing_file(self) -> None:
        result = analyze_file("nonexistent.py", root=Path("/tmp"))
        assert result.error is not None

    def test_extracts_function_arg_types(self) -> None:
        result = analyze_file("codemonkeys/core/runner.py", root=ROOT)
        runner = next(c for c in result.classes if c.name == "AgentRunner")
        run_agent = next(m for m in runner.methods if m.name == "run_agent")
        arg_names = [a["name"] for a in run_agent.args]
        assert "agent" in arg_names
        agent_arg = next(a for a in run_agent.args if a["name"] == "agent")
        assert agent_arg["type"] == "AgentDefinition"


class TestAnalyzeFiles:
    def test_batch_returns_all_results(self) -> None:
        files = [
            "codemonkeys/core/runner.py",
            "codemonkeys/workflows/compositions.py",
        ]
        results = analyze_files(files, root=ROOT)
        assert len(results) == 2
        assert all(isinstance(r, FileAnalysis) for r in results)

    def test_batch_tolerates_bad_files(self, tmp_path: Path) -> None:
        (tmp_path / "good.py").write_text("x = 1")
        (tmp_path / "bad.py").write_text("def broken(")
        results = analyze_files(["good.py", "bad.py"], root=tmp_path)
        assert results[0].error is None
        assert results[1].error is not None


class TestFormatAnalysis:
    def test_includes_file_headers(self) -> None:
        results = analyze_files(
            ["codemonkeys/core/runner.py", "codemonkeys/workflows/compositions.py"],
            root=ROOT,
        )
        text = format_analysis(results)
        assert "### `codemonkeys/core/runner.py`" in text
        assert "### `codemonkeys/workflows/compositions.py`" in text

    def test_shows_function_signatures(self, tmp_path: Path) -> None:
        code = dedent("""\
            async def fetch(url: str) -> dict:
                pass
        """)
        (tmp_path / "a.py").write_text(code)
        results = analyze_files(["a.py"], root=tmp_path)
        text = format_analysis(results)
        assert "async fetch(url: str) -> dict" in text

    def test_shows_class_with_bases(self, tmp_path: Path) -> None:
        code = dedent("""\
            class Dog(Animal):
                def bark(self) -> str:
                    return "woof"
        """)
        (tmp_path / "a.py").write_text(code)
        results = analyze_files(["a.py"], root=tmp_path)
        text = format_analysis(results)
        assert "class Dog(Animal):" in text
        assert "bark() -> str" in text

    def test_shows_internal_imports(self) -> None:
        results = analyze_files(["codemonkeys/workflows/compositions.py"], root=ROOT)
        text = format_analysis(results)
        assert "Internal imports:" in text
        assert "codemonkeys.workflows.phase_library" in text

    def test_shows_parse_error(self, tmp_path: Path) -> None:
        (tmp_path / "bad.py").write_text("def broken(")
        results = analyze_files(["bad.py"], root=tmp_path)
        text = format_analysis(results)
        assert "Parse error:" in text

    def test_shows_decorators(self, tmp_path: Path) -> None:
        code = dedent("""\
            def cached(f): return f

            @cached
            def expensive() -> int:
                return 42
        """)
        (tmp_path / "a.py").write_text(code)
        results = analyze_files(["a.py"], root=tmp_path)
        text = format_analysis(results)
        assert "@cached " in text

    def test_omits_self_from_method_args(self, tmp_path: Path) -> None:
        code = dedent("""\
            class Foo:
                def bar(self, x: int) -> None:
                    pass
        """)
        (tmp_path / "a.py").write_text(code)
        results = analyze_files(["a.py"], root=tmp_path)
        text = format_analysis(results)
        assert "bar(x: int)" in text
        assert "self" not in text
