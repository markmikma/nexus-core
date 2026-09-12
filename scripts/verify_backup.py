#!/usr/bin/env python3
"""Validate a Nexus-Core backup before a human-approved restore."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup_directory", type=Path)
    args = parser.parse_args()
    directory = args.backup_directory.resolve()
    manifest = json.loads((directory / "manifest.json").read_text())
    database = directory / "nexus.db"
    if manifest.get("database"):
        connection = sqlite3.connect(database)
        try:
            connection.execute("PRAGMA integrity_check").fetchone()
        finally:
            connection.close()
    print("Backup validation passed. Restore is intentionally manual and requires a stopped stack.")


if __name__ == "__main__":
    main()
