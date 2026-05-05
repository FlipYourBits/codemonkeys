from __future__ import annotations


from codemonkeys.tui.screens.analyzer import AnalyzerScreen


class TestAnalyzerScreen:
    def test_screen_instantiates(self) -> None:
        screen = AnalyzerScreen()
        assert screen is not None
