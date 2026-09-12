#!/usr/bin/env python3
"""Create a portable local backup without stopping Nexus-Core."""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def copy_sqlite(source: Path, destination: Path) -> None:
    source_connection = sqlite3.connect(source)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "backups")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = args.output_root / stamp
    target.mkdir(parents=True, exist_ok=False)

    database = PROJECT_ROOT / "data" / "nexus.db"
    if database.exists():
        copy_sqlite(database, target / "nexus.db")
    compose = PROJECT_ROOT / "infra" / "docker-compose.yml"
    shutil.copy2(compose, target / "docker-compose.yml")

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database": "nexus.db" if database.exists() else None,
        "compose_file": "docker-compose.yml",
        "scope": "SQLite control-plane state and Compose topology. Gitea repositories remain in infra/gitea_data and require a separate Gitea dump for off-host recovery.",
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(target)


if __name__ == "__main__":
    main()
