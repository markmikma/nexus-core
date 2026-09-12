"""Fail CI when tracked source files contain likely hard-coded secrets."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

PRIVATE_KEY = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
AWS_ACCESS_KEY = re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")
GITHUB_TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{36,255}|github_pat_[A-Za-z0-9_]{20,})\b")
GENERIC_CREDENTIAL = re.compile(
    r"(?m)^\s*(?:export\s+)?([A-Z][A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_KEY|APIKEY)[A-Z0-9_]*)\s*[:=]\s*[\"']?([^\s\"'#]+)"
)
ALLOW_MARKER = "nexus-secret-scan: allow"
PLACEHOLDER_VALUES = {
    "",
    "none",
    "null",
    "false",
    "true",
    "example",
    "placeholder",
    "change-me",
    "changeme",
    "not-set",
}


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def is_suppressed(text: str, offset: int) -> bool:
    line_start = text.rfind("\n", 0, offset) + 1
    line_end = text.find("\n", offset)
    return ALLOW_MARKER in text[line_start: line_end if line_end != -1 else None]


def is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        normalized in PLACEHOLDER_VALUES
        or normalized.startswith(("${", "$", "<", "your_", "replace_", "replace-with-"))
        or normalized.endswith("}")
    )


def is_code_expression(value: str) -> bool:
    return value.startswith(("re.", "os.", "settings.", "Path(", "str(", "int(", "bool(", "getattr("))


def scan_text(relative_path: str, text: str) -> list[dict]:
    findings: list[dict] = []
    patterns = (
        ("private-key", PRIVATE_KEY),
        ("aws-access-key", AWS_ACCESS_KEY),
        ("github-token", GITHUB_TOKEN),
    )
    for kind, pattern in patterns:
        for match in pattern.finditer(text):
            if is_suppressed(text, match.start()):
                continue
            findings.append(
                {"file": relative_path, "line": line_number(text, match.start()), "type": kind}
            )
    for match in GENERIC_CREDENTIAL.finditer(text):
        name, value = match.groups()
        if not is_placeholder(value) and not is_code_expression(value) and not is_suppressed(text, match.start()):
            findings.append(
                {
                    "file": relative_path,
                    "line": line_number(text, match.start()),
                    "type": "hard-coded-credential",
                    "name": name,
                }
            )
    return findings


def tracked_files(repository_root: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repository_root,
        check=True,
        capture_output=True,
    )
    return [
        repository_root / entry.decode("utf-8")
        for entry in completed.stdout.split(b"\0")
        if entry
    ]


def scan_repository(repository_root: Path) -> list[dict]:
    findings: list[dict] = []
    for file_path in tracked_files(repository_root):
        try:
            content = file_path.read_bytes()
        except OSError:
            continue
        if b"\0" in content:
            continue
        findings.extend(
            scan_text(str(file_path.relative_to(repository_root)), content.decode("utf-8", errors="replace"))
        )
    return findings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    args = parser.parse_args()

    repository = args.repository.resolve()
    findings = scan_repository(repository)
    report = {"scanner": "nexus-secret-scan", "findings": findings, "count": len(findings)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Secret scan completed: {args.output} ({len(findings)} finding(s))")
    if findings:
        raise SystemExit("Secret scan blocked the pipeline. Remove the secret and rotate it if it was real.")


if __name__ == "__main__":
    main()
