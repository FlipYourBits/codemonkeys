from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codemonkeys.workflows.compositions import ReviewConfig
from codemonkeys.workflows.phases import WorkflowContext


class TestMechanicalAudit:
    @pytest.mark.asyncio
    async def test_runs_ruff(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import mechanical_audit

        ruff_json = '[{"filename": "a.py", "location": {"row": 1}, "code": "F401", "message": "unused import"}]'

        with patch(
            "codemonkeys.workflows.phase_library.mechanical.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=1, stdout=ruff_json, stderr=""
            )
            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(mode="files", target_files=["a.py"]),
                phase_results={"discover": {"files": ["a.py"]}},
            )
            ctx.config.audit_tools = {"ruff"}
            result = await mechanical_audit(ctx)

        assert len(result["mechanical"].ruff) == 1
        assert result["mechanical"].ruff[0].code == "F401"

    @pytest.mark.asyncio
    async def test_skips_disabled_tools(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import mechanical_audit

        with patch(
            "codemonkeys.workflows.phase_library.mechanical.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(returncode=0, stdout="[]", stderr="")
            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(mode="files", target_files=["a.py"]),
                phase_results={"discover": {"files": ["a.py"]}},
            )
            ctx.config.audit_tools = {"ruff"}
            result = await mechanical_audit(ctx)

        assert result["mechanical"].pip_audit is None
        assert result["mechanical"].dead_code is None

    @pytest.mark.asyncio
    async def test_runs_pytest(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import mechanical_audit

        with patch(
            "codemonkeys.workflows.phase_library.mechanical.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout="5 passed\n", stderr=""
            )
            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(mode="files", target_files=["a.py"]),
                phase_results={"discover": {"files": ["a.py"]}},
            )
            ctx.config.audit_tools = {"pytest"}
            result = await mechanical_audit(ctx)

        assert result["mechanical"].pytest is not None
        assert result["mechanical"].pytest.passed == 5


class TestSecretsScanner:
    def test_detects_aws_key(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import _scan_secrets

        target = tmp_path / "config.py"
        target.write_text('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n')

        findings = _scan_secrets(["config.py"], tmp_path)
        assert len(findings) >= 1
        assert "AWS" in findings[0].pattern

    def test_no_false_positive_on_normal_code(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import _scan_secrets

        target = tmp_path / "clean.py"
        target.write_text("x = 42\nname = 'hello'\n")

        findings = _scan_secrets(["clean.py"], tmp_path)
        assert findings == []
