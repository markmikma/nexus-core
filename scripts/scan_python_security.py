#!/usr/bin/env python3
"""Fail a build when high-risk Python primitives are introduced."""
import argparse
import ast
import json
from pathlib import Path

DANGEROUS_NAMES = {"eval", "exec", "compile"}
PICKLE_NAMES = {"load", "loads"}


class SecurityVisitor(ast.NodeVisitor):
    def __init__(self, path: Path):
        self.path = path
        self.findings = []

    def add(self, node, rule, detail):
        self.findings.append({"file": str(self.path), "line": node.lineno, "rule": rule, "detail": detail})

    def visit_Call(self, node):
        name = node.func.id if isinstance(node.func, ast.Name) else ""
        attr = node.func.attr if isinstance(node.func, ast.Attribute) else ""
        module = node.func.value.id if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) else ""

        if name in DANGEROUS_NAMES:
            self.add(node, "dangerous-dynamic-execution", name)
        if module == "os" and attr == "system":
            self.add(node, "shell-command-execution", "os.system")
        if module == "pickle" and attr in PICKLE_NAMES:
            self.add(node, "unsafe-deserialization", f"pickle.{attr}")
        if module == "subprocess" and attr in {"run", "call", "Popen", "check_call", "check_output"}:
            for keyword in node.keywords:
                if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                    self.add(node, "shell-command-execution", f"subprocess.{attr}(shell=True)")
        self.generic_visit(node)


def scan(root: Path):
    findings = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or "venv" in path.parts:
            continue
        visitor = SecurityVisitor(path.relative_to(root))
        visitor.visit(ast.parse(path.read_text(), filename=str(path)))
        findings.extend(visitor.findings)
    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    findings = scan(args.repository.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"scanner": "nexus-python-sast", "findings": findings}, indent=2) + chr(10))
    print(f"SAST findings: {len(findings)}")
    raise SystemExit(1 if findings else 0)


if __name__ == "__main__":
    main()
