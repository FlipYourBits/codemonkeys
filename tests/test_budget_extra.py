"""Extra budget tests for default_on_warn and edge cases."""

from __future__ import annotations

from agentpipe.budget import default_on_warn


class TestDefaultOnWarn:
    def test_prints_warning(self, capsys):
        default_on_warn(0.5, 1.0)
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "$0.5000" in captured.err
        assert "50%" in captured.err

    def test_zero_budget_no_crash(self, capsys):
        default_on_warn(0.0, 0.0)
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "0%" in captured.err
