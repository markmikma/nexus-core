"""Image vulnerability scanning used by the deployment worker."""

import json
from pathlib import Path

from src.config import settings


def scan_image(docker_client, image_reference: str, report_path: Path | None = None) -> dict:
    """Blocks promotion when Trivy reports a policy-matching vulnerability.

    The scanner runs in a short-lived container and uses a named Docker volume for
    its vulnerability database. Unfixed findings are retained in Trivy reports but
    do not block delivery while no upstream patch exists.
    """
    if not settings.image_scan_enabled:
        return {"enabled": False, "findings": 0}

    command = [
        "image",
        "--format",
        "json",
        "--scanners",
        "vuln",
        "--severity",
        settings.image_scan_severities,
        "--exit-code",
        "0",
        "--no-progress",
    ]
    if settings.trivy_ignore_unfixed:
        command.append("--ignore-unfixed")
    command.append(image_reference)

    output = docker_client.containers.run(
        image=settings.trivy_image,
        command=command,
        volumes={
            "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "ro"},
            settings.trivy_cache_volume: {"bind": "/root/.cache/trivy", "mode": "rw"},
        },
        remove=True,
    )
    report = json.loads(output.decode("utf-8"))
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    findings = [
        vulnerability
        for result in report.get("Results", [])
        for vulnerability in result.get("Vulnerabilities") or []
    ]
    summary = {
        "enabled": True,
        "findings": len(findings),
        "severities": settings.image_scan_severities,
        "ignore_unfixed": settings.trivy_ignore_unfixed,
    }
    if findings:
        identifiers = ", ".join(
            f"{item.get('PkgName')}:{item.get('VulnerabilityID')}" for item in findings[:5]
        )
        raise RuntimeError(
            f"Image security gate blocked {image_reference}: {len(findings)} finding(s) "
            f"at {settings.image_scan_severities}. {identifiers}"
        )
    return summary
