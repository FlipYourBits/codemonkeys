from __future__ import annotations

import pytest

from codemonkeys.tui.app import CodemonkeysApp


class TestCodemonkeysApp:
    @pytest.mark.asyncio
    async def test_app_starts_and_shows_home(self) -> None:
        app = CodemonkeysApp()
        async with app.run_test() as _pilot:
            assert app.title == "codemonkeys"
            assert len(app.query("HomeContent")) == 1

    @pytest.mark.asyncio
    async def test_app_has_header_and_footer(self) -> None:
        app = CodemonkeysApp()
        async with app.run_test() as _pilot:
            header = app.query("Header")
            footer = app.query("Footer")
            assert len(header) == 1
            assert len(footer) == 1
