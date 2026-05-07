from __future__ import annotations

import json
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
            "codemonkeys.workflows.phase_library._mechanical_tools.subprocess"
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
            "codemonkeys.workflows.phase_library._mechanical_tools.subprocess"
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
    async def test_runs_license_compliance(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import mechanical_audit
        import json

        pip_licenses_json = json.dumps(
            [{"Name": "gpl-lib", "Version": "1.0", "License": "GPL-3.0"}]
        )

        with patch(
            "codemonkeys.workflows.phase_library._mechanical_license.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=pip_licenses_json, stderr=""
            )
            ctx = WorkflowContext(
                cwd=str(tmp_path),
                run_id="test/run1",
                config=ReviewConfig(mode="files", target_files=["a.py"]),
                phase_results={"discover": {"files": ["a.py"]}},
            )
            ctx.config.audit_tools = {"license_compliance"}
            result = await mechanical_audit(ctx)

        assert result["mechanical"].license_compliance is not None
        assert len(result["mechanical"].license_compliance) == 1

    @pytest.mark.asyncio
    async def test_runs_release_hygiene(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import mechanical_audit

        target = tmp_path / "app.py"
        target.write_text("breakpoint()\n")

        ctx = WorkflowContext(
            cwd=str(tmp_path),
            run_id="test/run1",
            config=ReviewConfig(mode="files", target_files=["app.py"]),
            phase_results={"discover": {"files": ["app.py"]}},
        )
        ctx.config.audit_tools = {"release_hygiene"}
        result = await mechanical_audit(ctx)

        assert result["mechanical"].release_hygiene is not None
        assert len(result["mechanical"].release_hygiene) >= 1

    @pytest.mark.asyncio
    async def test_runs_pytest(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library.mechanical import mechanical_audit

        with patch(
            "codemonkeys.workflows.phase_library._mechanical_tools.subprocess"
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
        from codemonkeys.workflows.phase_library._mechanical_tools import _scan_secrets

        target = tmp_path / "config.py"
        target.write_text('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n')

        findings = _scan_secrets(["config.py"], tmp_path)
        assert len(findings) >= 1
        assert "AWS" in findings[0].pattern

    def test_no_false_positive_on_normal_code(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_tools import _scan_secrets

        target = tmp_path / "clean.py"
        target.write_text("x = 42\nname = 'hello'\n")

        findings = _scan_secrets(["clean.py"], tmp_path)
        assert findings == []


class TestLicenseCompliance:
    def test_classifies_gpl_as_copyleft(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_license import (
            _run_license_compliance,
        )

        piplicenses_json = json.dumps(
            [
                {"Name": "some-gpl-pkg", "Version": "1.0", "License": "GPL-3.0"},
                {"Name": "safe-pkg", "Version": "2.0", "License": "MIT"},
            ]
        )

        with patch(
            "codemonkeys.workflows.phase_library._mechanical_license.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=piplicenses_json, stderr=""
            )
            findings = _run_license_compliance(tmp_path)

        assert len(findings) == 1
        assert findings[0].package == "some-gpl-pkg"
        assert findings[0].category == "copyleft_risk"
        assert findings[0].severity == "high"

    def test_classifies_unknown_license(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_license import (
            _run_license_compliance,
        )

        piplicenses_json = json.dumps(
            [
                {"Name": "mystery-pkg", "Version": "0.1", "License": "UNKNOWN"},
            ]
        )

        with patch(
            "codemonkeys.workflows.phase_library._mechanical_license.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=piplicenses_json, stderr=""
            )
            findings = _run_license_compliance(tmp_path)

        assert len(findings) == 1
        assert findings[0].category == "unknown_license"
        assert findings[0].severity == "medium"

    def test_permissive_licenses_pass(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_license import (
            _run_license_compliance,
        )

        piplicenses_json = json.dumps(
            [
                {"Name": "pkg-a", "Version": "1.0", "License": "MIT"},
                {"Name": "pkg-b", "Version": "2.0", "License": "BSD-3-Clause"},
                {"Name": "pkg-c", "Version": "3.0", "License": "Apache-2.0"},
                {"Name": "pkg-d", "Version": "4.0", "License": "ISC"},
            ]
        )

        with patch(
            "codemonkeys.workflows.phase_library._mechanical_license.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=piplicenses_json, stderr=""
            )
            findings = _run_license_compliance(tmp_path)

        assert findings == []

    def test_classifies_restrictive_license(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_license import (
            _run_license_compliance,
        )

        piplicenses_json = json.dumps(
            [
                {"Name": "mpl-pkg", "Version": "1.0", "License": "MPL-2.0"},
            ]
        )

        with patch(
            "codemonkeys.workflows.phase_library._mechanical_license.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=piplicenses_json, stderr=""
            )
            findings = _run_license_compliance(tmp_path)

        assert len(findings) == 1
        assert findings[0].category == "restrictive_license"
        assert findings[0].severity == "low"

    def test_classifies_non_standard_license(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_license import (
            _run_license_compliance,
        )

        piplicenses_json = json.dumps(
            [
                {
                    "Name": "custom-pkg",
                    "Version": "1.0",
                    "License": "Custom License v3",
                },
            ]
        )

        with patch(
            "codemonkeys.workflows.phase_library._mechanical_license.subprocess"
        ) as mock_sub:
            mock_sub.run.return_value = MagicMock(
                returncode=0, stdout=piplicenses_json, stderr=""
            )
            findings = _run_license_compliance(tmp_path)

        assert len(findings) == 1
        assert findings[0].category == "non_standard_license"
        assert findings[0].severity == "low"


class TestReleaseHygiene:
    def test_detects_breakpoint(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_hygiene import (
            _run_release_hygiene,
        )

        (tmp_path / "app.py").write_text("x = 1\nbreakpoint()\ny = 2\n")
        (tmp_path / "uv.lock").write_text("")

        findings = _run_release_hygiene(["app.py"], tmp_path)
        debug_findings = [f for f in findings if f.category == "debug_artifact"]
        assert len(debug_findings) == 1
        assert debug_findings[0].line == 2
        assert debug_findings[0].detail == "breakpoint() call"

    def test_detects_import_pdb(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_hygiene import (
            _run_release_hygiene,
        )

        (tmp_path / "app.py").write_text("import pdb\npdb.set_trace()\n")
        (tmp_path / "uv.lock").write_text("")

        findings = _run_release_hygiene(["app.py"], tmp_path)
        debug_findings = [f for f in findings if f.category == "debug_artifact"]
        assert len(debug_findings) >= 1
        assert any(f.detail == "pdb import" for f in debug_findings)

    def test_skips_print_in_test_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_hygiene import (
            _run_release_hygiene,
        )

        (tmp_path / "test_app.py").write_text('print("hello")\n')
        (tmp_path / "uv.lock").write_text("")

        findings = _run_release_hygiene(["test_app.py"], tmp_path)
        print_findings = [
            f
            for f in findings
            if f.category == "debug_artifact" and "print" in f.detail
        ]
        assert print_findings == []

    def test_detects_bare_todo(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_hygiene import (
            _run_release_hygiene,
        )

        (tmp_path / "app.py").write_text("# TODO fix this later\n")
        (tmp_path / "uv.lock").write_text("")

        findings = _run_release_hygiene(["app.py"], tmp_path)
        marker_findings = [f for f in findings if f.category == "unresolved_marker"]
        assert len(marker_findings) == 1

    def test_allows_todo_with_issue_ref(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_hygiene import (
            _run_release_hygiene,
        )

        (tmp_path / "app.py").write_text("# TODO(#123) fix this later\n")
        (tmp_path / "uv.lock").write_text("")

        findings = _run_release_hygiene(["app.py"], tmp_path)
        marker_findings = [f for f in findings if f.category == "unresolved_marker"]
        assert marker_findings == []

    def test_detects_localhost(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_hygiene import (
            _run_release_hygiene,
        )

        (tmp_path / "client.py").write_text('URL = "http://localhost:8080/api"\n')
        (tmp_path / "uv.lock").write_text("")

        findings = _run_release_hygiene(["client.py"], tmp_path)
        dev_findings = [f for f in findings if f.category == "hardcoded_dev_value"]
        assert len(dev_findings) >= 1
        assert dev_findings[0].severity == "high"

    def test_skips_localhost_in_test_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_hygiene import (
            _run_release_hygiene,
        )

        (tmp_path / "test_client.py").write_text('URL = "http://localhost:8080/api"\n')
        (tmp_path / "uv.lock").write_text("")

        findings = _run_release_hygiene(["test_client.py"], tmp_path)
        dev_findings = [f for f in findings if f.category == "hardcoded_dev_value"]
        assert dev_findings == []

    def test_skips_localhost_in_config_files(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_hygiene import (
            _run_release_hygiene,
        )

        (tmp_path / "config.py").write_text('URL = "http://localhost:8080/api"\n')
        (tmp_path / "uv.lock").write_text("")

        findings = _run_release_hygiene(["config.py"], tmp_path)
        dev_findings = [f for f in findings if f.category == "hardcoded_dev_value"]
        assert dev_findings == []

    def test_detects_missing_lockfile(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_hygiene import (
            _run_release_hygiene,
        )

        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")

        findings = _run_release_hygiene(["pyproject.toml"], tmp_path)
        dep_findings = [f for f in findings if f.category == "dependency_pinning"]
        assert len(dep_findings) == 1
        assert "lockfile" in dep_findings[0].detail.lower()

    def test_no_lockfile_finding_when_present(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_hygiene import (
            _run_release_hygiene,
        )

        (tmp_path / "app.py").write_text("x = 1\n")
        (tmp_path / "uv.lock").write_text("")

        findings = _run_release_hygiene(["app.py"], tmp_path)
        dep_findings = [f for f in findings if f.category == "dependency_pinning"]
        assert dep_findings == []

    def test_clean_file_no_findings(self, tmp_path: Path) -> None:
        from codemonkeys.workflows.phase_library._mechanical_hygiene import (
            _run_release_hygiene,
        )

        (tmp_path / "app.py").write_text(
            "def greet(name: str) -> str:\n    return f'Hello, {name}'\n"
        )
        (tmp_path / "uv.lock").write_text("")

        findings = _run_release_hygiene(["app.py"], tmp_path)
        assert findings == []
