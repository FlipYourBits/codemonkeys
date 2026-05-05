from __future__ import annotations

from unittest.mock import patch

from codemonkeys.cli import main


class TestCLI:
    @patch("codemonkeys.cli.CodemonkeysApp")
    @patch("codemonkeys.cli.restrict")
    def test_main_calls_restrict_and_runs_app(
        self, mock_restrict, mock_app_cls
    ) -> None:
        mock_app = mock_app_cls.return_value
        main()
        mock_restrict.assert_called_once()
        mock_app.run.assert_called_once()
