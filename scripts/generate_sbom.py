"""Generate a minimal CycloneDX SBOM from Python requirements files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

PACKAGE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*(?:==\s*([^\s;]+))?")


def components(requirement_files: list[Path]) -> list[dict]:
    found: dict[str, dict] = {}
    for file_path in requirement_files:
        for raw_line in file_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or line.startswith(("-", "http")):
                continue
            match = PACKAGE.match(line)
            if not match:
                continue
            name, version = match.groups()
            key = name.lower().replace("_", "-")
            found[key] = {
                "type": "library",
                "name": name,
                "version": version or "unresolved",
                "purl": f"pkg:pypi/{key}@{version}" if version else f"pkg:pypi/{key}",
                "properties": [{"name": "nexus:source", "value": str(file_path)}],
            }
    return [found[key] for key in sorted(found)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("requirements", nargs="+", type=Path)
    args = parser.parse_args()

    for requirements_file in args.requirements:
        if not requirements_file.is_file():
            raise SystemExit(f"Requirements file not found: {requirements_file}")

    serial = "|".join(str(path) for path in args.requirements)
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{hashlib.sha256(serial.encode()).hexdigest()[:32]}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools": [{"vendor": "Nexus-Core", "name": "generate_sbom.py"}],
        },
        "components": components(args.requirements),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"SBOM generated: {args.output} ({len(document['components'])} components)")


if __name__ == "__main__":
    main()
