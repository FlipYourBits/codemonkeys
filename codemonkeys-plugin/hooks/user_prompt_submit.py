"""UserPromptSubmit hook — run mechanical checks before python-review skill."""
from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


SKILL_TRIGGER = "/codemonkeys:python-review"


def main() -> None:
    data = json.loads(sys.stdin.read())
    prompt = data.get("prompt", "")
    cwd = Path(data.get("cwd", ".")).resolve()

    if SKILL_TRIGGER not in prompt:
        sys.exit(0)

    codemonkeys_dir = cwd / ".codemonkeys"
    results_dir = codemonkeys_dir / "check-results"
    results_dir.mkdir(parents=True, exist_ok=True)

    active_skill = codemonkeys_dir / ".active-skill"
    active_skill.parent.mkdir(parents=True, exist_ok=True)
    active_skill.write_text("python-review")

    file_args = _parse_file_args(prompt)

    checks = {
        "ruff": (_run_ruff, file_args, results_dir, cwd),
        "pyright": (_run_pyright, file_args, results_dir, cwd),
        "pytest": (_run_pytest, results_dir, cwd),
        "pip-audit": (_run_pip_audit, results_dir, cwd),
    }

    summaries = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {}
        for name, args in checks.items():
            fn = args[0]
            fn_args = args[1:]
            futures[pool.submit(fn, *fn_args)] = name

        for future in as_completed(futures):
            name = futures[future]
            try:
                summaries[name] = future.result()
            except Exception as exc:
                summaries[name] = f"error ({exc})"

    parts = [f"{name}: {summary}" for name, summary in sorted(summaries.items())]
    print("[codemonkeys] " + " | ".join(parts))


def _parse_file_args(prompt: str) -> list[str]:
    parts = prompt.split(SKILL_TRIGGER, 1)
    if len(parts) < 2:
        return []
    remainder = parts[1].strip()
    if not remainder:
        return []
    return remainder.split()


def _tool_available(module: str) -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-m", module, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _run_ruff(file_args: list[str], results_dir: Path, cwd: Path) -> str:
    if not _tool_available("ruff"):
        return "not installed"

    targets = file_args if file_args else ["."]
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--output-format", "json", *targets],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    (results_dir / "ruff.json").write_text(result.stdout or "[]")

    try:
        findings = json.loads(result.stdout or "[]")
        count = len(findings)
    except json.JSONDecodeError:
        return "parse error"
    return f"{count} errors" if count > 0 else "clean"


def _run_pyright(file_args: list[str], results_dir: Path, cwd: Path) -> str:
    if not _tool_available("pyright"):
        return "not installed"

    targets = file_args if file_args else ["."]
    result = subprocess.run(
        [sys.executable, "-m", "pyright", "--outputjson", *targets],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    (results_dir / "pyright.json").write_text(result.stdout or "{}")

    try:
        data = json.loads(result.stdout or "{}")
        count = data.get("summary", {}).get("errorCount", 0)
    except json.JSONDecodeError:
        return "parse error"
    return f"{count} errors" if count > 0 else "clean"


def _run_pytest(results_dir: Path, cwd: Path) -> str:
    if not _tool_available("pytest"):
        return "not installed"

    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "--cov", "--cov-report=json", "--cov-report=term",
            "-x", "-q", "--tb=short", "--no-header",
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
    )

    output = {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    cov_json = cwd / "coverage.json"
    if cov_json.exists():
        try:
            output["coverage"] = json.loads(cov_json.read_text())
        except json.JSONDecodeError:
            pass

    (results_dir / "pytest.json").write_text(json.dumps(output, indent=2))

    last_line = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if result.returncode == 0:
        return last_line or "passed"
    return f"FAILED — {last_line}" if last_line else "FAILED"


def _run_pip_audit(results_dir: Path, cwd: Path) -> str:
    if not _tool_available("pip_audit"):
        return "not installed"

    result = subprocess.run(
        [sys.executable, "-m", "pip_audit", "--format", "json", "--strict", "--desc"],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    (results_dir / "pip-audit.json").write_text(result.stdout or "[]")

    try:
        findings = json.loads(result.stdout or "[]")
        count = len(findings)
    except json.JSONDecodeError:
        return "parse error"
    return f"{count} vulnerabilities" if count > 0 else "clean"


if __name__ == "__main__":
    main()
