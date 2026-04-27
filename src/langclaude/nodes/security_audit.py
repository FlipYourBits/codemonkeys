"""Security-audit node: Claude agent that runs scanners and reviews for vulnerabilities.

Claude probes for installed scanners (semgrep, gitleaks, pip-audit,
npm audit, etc.), runs them, then performs semantic security review
and triage following the security-audit skill.

When Edit/Write are in the allow list (and not denied), the agent also
fixes vulnerabilities it finds. Control interactive vs auto approval via
on_unmatched.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from langclaude.models import DEFAULT
from langclaude.nodes.base import ClaudeAgentNode
from langclaude.permissions import UnmatchedPolicy

Mode = Literal["diff", "full"]

_SKILL = """\

# Security audit

You are conducting a security audit of a code repository. Your goal is to identify high-confidence, exploitable vulnerabilities — not theoretical or stylistic issues. Better to miss speculative findings than flood the report with false positives.

## Scope

- **Diff mode**: only review changes between the base ref given in the user prompt and `HEAD`. Do not flag pre-existing issues outside the diff.
- **Full mode**: review the entire current tree.

The user's prompt will tell you which mode and (in diff mode) which base ref to use.

## Phase 1 — Pre-collected scanner output

Scanner output (semgrep, gitleaks, pip-audit, npm audit, govulncheck, cargo audit, bundler-audit, trivy) is already collected by a deterministic shell node and injected into your prompt. Do not re-run these tools. Treat their output as **leads, not verdicts** — you must still confirm exploitability by reading the code before reporting.

## Phase 2 — Semantic review

For diff mode, run `git diff BASE_REF...HEAD` (substituting the base ref from the user prompt) and read every changed file. For full mode, walk the tree (use `Glob` + `Read`).

Trace data flow from untrusted inputs (HTTP handlers, CLI args, env vars, queue consumers, file ingest, IPC) to sinks. Look for:

### Injection
- SQL via string concat / f-strings into raw queries
- Command injection via `subprocess(shell=True)`, `os.system`, backticks, `exec`
- Path traversal — user-controlled paths joined to filesystem operations without confining to a base dir
- XXE — XML parsers with external entity resolution enabled
- SSRF — outbound requests built from user input without host allowlist
- Template injection — user input rendered through Jinja/EJS/etc. as template, not data
- LDAP / NoSQL / GraphQL injection where applicable

### Authentication & authorization
- Authn bypass paths (missing `@require_auth`, conditional skips)
- Authorization checks at the wrong layer (UI-only, missing on API)
- IDOR — operations that trust a client-supplied resource ID without ownership check
- JWT issues — `alg: none` accepted, no signature verification, weak secret, missing `exp`
- Session fixation, missing httpOnly/secure cookie flags on auth cookies

### Secrets & crypto
- Hardcoded keys, tokens, passwords, connection strings (cross-check with gitleaks output)
- Weak hashes for passwords (raw SHA, MD5) — should be bcrypt/argon2/scrypt
- Weak crypto primitives (DES, RC4, ECB mode, PKCS#1 v1.5)
- Predictable randomness for security-critical values (`random` instead of `secrets`)
- TLS verification disabled (`verify=False`, `rejectUnauthorized: false`)
- Missing `secrets.compare_digest` for token comparison (timing attack)

### Code execution
- Unsafe deserialization — `pickle.loads`, `yaml.load` (without `SafeLoader`), Java `ObjectInputStream`, .NET `BinaryFormatter`, Ruby `Marshal.load`, PHP `unserialize`
- Dynamic code execution — `eval`, `exec`, `Function()`, `setTimeout(string)`, dynamic `require`/`import` from user input
- XSS — user input rendered into HTML without escaping (reflected/stored/DOM)
- Prototype pollution in JS — recursive merges over user-controlled objects

### Data exposure
- PII / credentials in logs, error responses, or debug output
- Verbose stack traces returned to clients
- Missing redaction in telemetry
- Overly broad CORS (`*` with credentials)

### Other
- Race conditions on auth or financial state (TOCTOU)
- Missing rate limits on auth endpoints (only flag if it enables credential stuffing — not generic DoS)
- Insecure defaults in framework config

## Phase 3 — Triage and dedupe

- Cross-reference scanner findings against your semantic review. Drop scanner findings you cannot confirm by reading the code.
- Drop duplicates (same vuln reported by multiple sources — keep the one with strongest evidence).
- Apply confidence threshold: report only findings ≥ 0.8 confidence of real exploitability. Below that, drop.

## Exclusions — DO NOT REPORT

- Denial of service or resource exhaustion (CPU, memory, file handles)
- Generic rate limiting concerns
- Lack of input validation on fields with no security impact
- Style, naming, or maintainability concerns
- Performance issues
- Pre-existing issues outside the diff (in diff mode)

## Output

Your final reply must be a single fenced JSON block matching this schema, and nothing else after it:

```json
{
  "mode": "diff" | "full",
  "scanners_run": ["semgrep", "gitleaks", "pip-audit"],
  "scanners_skipped": ["npm audit"],
  "findings": [
    {
      "file": "path/to/file.py",
      "line": 42,
      "severity": "HIGH" | "MEDIUM" | "LOW",
      "category": "sql_injection",
      "source": "semantic" | "semgrep" | "gitleaks" | "pip-audit" | "npm-audit" | "govulncheck" | "cargo-audit" | "trivy",
      "description": "User input passed to SQL query without parameterization.",
      "exploit_scenario": "Attacker sends '1; DROP TABLE users--' as the search param, dropping the users table.",
      "recommendation": "Use parameterized queries (cursor.execute(query, (param,))).",
      "confidence": 0.95
    }
  ],
  "summary": {
    "files_reviewed": 12,
    "high": 1,
    "medium": 0,
    "low": 0
  }
}
```

Severity guide:
- **HIGH**: directly exploitable → RCE, auth bypass, data breach, account takeover
- **MEDIUM**: exploitable under specific but realistic conditions
- **LOW**: defense-in-depth or limited-impact issues

If there are no findings, return the JSON with an empty `findings` array."""

_REVIEW_ONLY_PROMPT = (
    "You are a senior security engineer auditing a code repository. "
    "Use Bash to run git diff and any installed security scanners "
    "(semgrep, gitleaks, pip-audit, npm audit, govulncheck, cargo audit, "
    "trivy, etc.) — only run tools that are installed. "
    "Then perform semantic security review and triage following the "
    "skill below. Do not edit files; do not push. "
    "Output JSON only as your final message." + _SKILL
)

_REVIEW_AND_FIX_PROMPT = (
    "You are a senior security engineer auditing a code repository. "
    "Use Bash to run git diff and any installed security scanners "
    "(semgrep, gitleaks, pip-audit, npm audit, govulncheck, cargo audit, "
    "trivy, etc.) — only run tools that are installed. "
    "Then perform semantic security review and triage following the "
    "skill below. After reviewing, fix each vulnerability you "
    "found — make the smallest correct change per issue, verify by "
    "re-reading the file. Do not push. "
    "Output JSON only as your final message." + _SKILL
)

_READONLY_ALLOW: tuple[str, ...] = ("Read", "Glob", "Grep", "Bash")

_READONLY_DENY: tuple[str, ...] = (
    "Edit",
    "Write",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
    "Bash(git checkout*)",
    "Bash(curl*)",
    "Bash(wget*)",
)

_READWRITE_DENY: tuple[str, ...] = (
    "Bash(rm -rf*)",
    "Bash(rm*)",
    "Bash(git push*)",
    "Bash(git commit*)",
    "Bash(git reset*)",
    "Bash(git checkout*)",
    "Bash(curl*)",
    "Bash(wget*)",
)


def _has_write_tools(allow: Sequence[str]) -> bool:
    allow_names = {a.split("(")[0] for a in allow}
    return "Edit" in allow_names or "Write" in allow_names


def claude_security_audit_node(
    *,
    name: str = "security_audit",
    mode: Mode = "diff",
    base_ref_key: str = "base_ref",
    extra_skills: Sequence[str | Path] = (),
    allow: Sequence[str] | None = None,
    deny: Sequence[str] | None = None,
    on_unmatched: UnmatchedPolicy = "deny",
    model: str | None = DEFAULT,
    max_turns: int | None = None,
    output_key: str = "security_findings",
    verbose: bool = False,
    **kwargs: Any,
) -> ClaudeAgentNode:
    """Build a security-audit node.

    By default the node is read-only (Edit/Write denied). To enable
    fixing, pass allow=["Read", "Glob", "Grep", "Bash", "Edit", "Write"]
    and a deny list without Edit/Write. The system prompt adjusts
    automatically.

    State input:
        working_dir: repo root.
        base_ref (or ``base_ref_key``): git ref for diff mode.

    State output:
        ``output_key`` (default ``security_findings``): fenced JSON block.
    """
    if allow is not None:
        allow_list = list(allow)
    else:
        allow_list = list(_READONLY_ALLOW)

    if deny is not None:
        deny_list = list(deny)
    else:
        deny_list = list(
            _READONLY_DENY if not _has_write_tools(allow_list) else _READWRITE_DENY
        )

    can_fix = _has_write_tools(allow_list)
    system_prompt = _REVIEW_AND_FIX_PROMPT if can_fix else _REVIEW_ONLY_PROMPT

    if mode == "diff":
        prompt_template = (
            "DIFF mode — report only vulnerabilities introduced by the "
            "diff against {%s}. Start by running `git diff {%s}...HEAD` "
            "and any installed security scanners. "
            "Then proceed to semantic review and triage."
        ) % (base_ref_key, base_ref_key)
    else:
        prompt_template = (
            "FULL mode — audit the repository at {working_dir}. "
            "Start by listing files and running any installed security "
            "scanners. Then proceed to semantic review and triage."
        )

    return ClaudeAgentNode(
        name=name,
        system_prompt=system_prompt,
        skills=[*extra_skills],
        allow=allow_list,
        deny=deny_list,
        on_unmatched=on_unmatched,
        prompt_template=prompt_template,
        output_key=output_key,
        model=model,
        max_turns=max_turns,
        verbose=verbose,
        **kwargs,
    )
