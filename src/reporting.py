"""Persistent, token-protected security evidence storage."""

import re
from pathlib import Path

from src.config import settings

REPORT_FILENAMES = {
    "secret-scan": "secret-scan.json",
    "sbom": "sbom.cdx.json",
    "image-scan": "image-scan.json",
    "python-sast": "python-sast.json",
}
COMMIT_HASH = re.compile(r"[0-9a-f]{40}")


def report_directory(commit_hash: str) -> Path:
    if not COMMIT_HASH.fullmatch(commit_hash):
        raise ValueError("Invalid commit hash.")
    return settings.database_path.parent / "security-reports" / commit_hash


def report_path(commit_hash: str, report_type: str) -> Path:
    filename = REPORT_FILENAMES.get(report_type)
    if filename is None:
        raise ValueError("Unknown report type.")
    return report_directory(commit_hash) / filename


def list_reports(commit_hash: str) -> list[dict]:
    directory = report_directory(commit_hash)
    reports = []
    for report_type, filename in REPORT_FILENAMES.items():
        path = directory / filename
        if path.is_file():
            reports.append({"type": report_type, "filename": filename, "bytes": path.stat().st_size})
    return reports
