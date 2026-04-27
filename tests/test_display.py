from __future__ import annotations


from agentpipe.display import Display
from agentpipe.nodes.base import _make_printer, Verbosity


class TestDisplayNonLive:
    """Test Display with live=False (non-TTY / CI fallback)."""

    def test_construct_with_steps(self):
        d = Display(steps=["lint", "test"], title="Test", live=False)
        assert d.title == "Test"

    def test_node_start_prints(self, capsys):
        d = Display(steps=["lint"], title="T", live=False)
        d.node_start("lint")
        err = capsys.readouterr().err
        assert "lint" in err

    def test_node_done_prints(self, capsys):
        d = Display(steps=["lint"], title="T", live=False)
        d.node_start("lint")
        d.node_done("lint", elapsed=1.5, cost=0.0)
        err = capsys.readouterr().err
        assert "done" in err
        assert "1.5" in err

    def test_node_done_with_cost(self, capsys):
        d = Display(steps=["lint"], title="T", live=False)
        d.node_start("lint")
        d.node_done("lint", elapsed=2.0, cost=0.0312)
        err = capsys.readouterr().err
        assert "$0.0312" in err

    def test_node_output_prints(self, capsys):
        d = Display(steps=["lint"], title="T", live=False)
        d.node_start("lint")
        d.node_output("lint", "→ Read(foo.py)")
        err = capsys.readouterr().err
        assert "Read(foo.py)" in err

    def test_node_skip_prints(self, capsys):
        d = Display(steps=["lint"], title="T", live=False)
        d.node_skip("lint")
        err = capsys.readouterr().err
        assert "lint" in err

    def test_warn_prints_yellow(self, capsys):
        d = Display(steps=[], title="T", live=False)
        d.warn("budget exceeded")
        err = capsys.readouterr().err
        assert "budget exceeded" in err

    def test_prompt_returns_input(self, monkeypatch):
        d = Display(steps=[], title="T", live=False)
        monkeypatch.setattr("builtins.input", lambda *_: "yes")
        result = d.prompt("Continue?")
        assert result == "yes"

    def test_prompt_with_content(self, capsys, monkeypatch):
        d = Display(steps=[], title="T", live=False)
        monkeypatch.setattr("builtins.input", lambda *_: "y")
        d.prompt("Approve?", content="Here is the plan")
        err = capsys.readouterr().err
        assert "plan" in err

    def test_print_results_table(self, capsys):
        d = Display(steps=["a", "b"], title="T", live=False)
        d.print_results({"a": 0.05, "b": 0.10})
        out = capsys.readouterr().out
        assert "a" in out
        assert "b" in out
        assert "total" in out.lower() or "Total" in out

    def test_stop_is_safe_when_not_live(self):
        d = Display(steps=[], title="T", live=False)
        d.stop()  # should not raise


class TestDisplayLive:
    """Test Display with live=True but mocked stderr.isatty."""

    def test_live_starts_when_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stderr.isatty", lambda: True)
        d = Display(steps=["a"], title="T", live=True)
        assert d._live is not None
        d.stop()

    def test_live_skipped_when_not_tty(self, monkeypatch):
        monkeypatch.setattr("sys.stderr.isatty", lambda: False)
        d = Display(steps=["a"], title="T", live=True)
        assert d._live is None

    def test_node_lifecycle(self, monkeypatch):
        monkeypatch.setattr("sys.stderr.isatty", lambda: True)
        d = Display(steps=["a", "b"], title="T", live=True)
        d.node_start("a")
        d.node_output("a", "→ Read(x.py)")
        d.node_done("a", elapsed=1.0, cost=0.01)
        d.node_start("b")
        d.node_done("b", elapsed=0.5)
        d.stop()
        assert d._live is None

    def test_prompt_pauses_live(self, monkeypatch):
        monkeypatch.setattr("sys.stderr.isatty", lambda: True)
        d = Display(steps=["a"], title="T", live=True)
        d.node_start("a")

        monkeypatch.setattr("builtins.input", lambda *_: "yes")
        result = d.prompt("Continue?")
        assert result == "yes"
        # Live should have restarted
        assert d._live is not None
        d.stop()

    def test_stop_idempotent(self, monkeypatch):
        monkeypatch.setattr("sys.stderr.isatty", lambda: True)
        d = Display(steps=["a"], title="T", live=True)
        d.stop()
        d.stop()  # should not raise


class TestMakePrinterWithDisplay:
    def test_verbose_printer_routes_to_display(self):
        d = Display(steps=["test_node"], title="T", live=False)
        printer = _make_printer(Verbosity.verbose, display=d)
        assert printer is not None
