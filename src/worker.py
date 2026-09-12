import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from src.config import settings
from src.db import (
    claim_next_deployment,
    finish_deployment,
    init_db,
    recover_interrupted_deployments,
)
from src.docker_engine import build_and_deploy_app
from src.security import audit_python_dependencies
from src.reporting import report_directory, report_path

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("nexus.deployment-worker")

WORKSPACE_ROOT = Path("/workspace/jobs")

SSH_KEY_PATH = "/run/secrets/gitea_deploy_key"
KNOWN_HOSTS_PATH = "/run/secrets/gitea_known_hosts"


def run_git(arguments: list[str], cwd: Path | None = None) -> None:
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GIT_SSH_COMMAND"] = (
        f"ssh -i {SSH_KEY_PATH} "
        "-o IdentitiesOnly=yes "
        f"-o UserKnownHostsFile={KNOWN_HOSTS_PATH} "
        "-o StrictHostKeyChecking=yes"
    )

    completed = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"Git parancs sikertelen: {details}")


def checkout_exact_commit(job: dict) -> Path:
    if not settings.repository_url:
        raise RuntimeError("Hiányzik a GITEA_REPOSITORY_URL beállítás.")

    commit_hash = job["commit_hash"]
    workspace = WORKSPACE_ROOT / f"job-{job['id']}"

    shutil.rmtree(workspace, ignore_errors=True)
    workspace.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Repository klónozása: job=%s", job["id"])
    run_git(["clone", "--no-checkout", settings.repository_url, str(workspace)])

    logger.info("Konkrét commit checkout: %s", commit_hash)
    run_git(["checkout", "--detach", commit_hash], cwd=workspace)

    return workspace


def generate_security_evidence(workspace: Path, commit_hash: str) -> Path:
    """Rebuild CI security reports from the exact deploy commit."""
    directory = report_directory(commit_hash)
    directory.mkdir(parents=True, exist_ok=True)
    commands = (
        (["python", "scripts/scan_secrets.py", "--repository", str(workspace), "--output", str(report_path(commit_hash, "secret-scan"))], "Secret scan"),
        (["python", "scripts/generate_sbom.py", "--output", str(report_path(commit_hash, "sbom")), "requirements.txt", "apps/sample-app/requirements.txt"], "SBOM generation"),
    )
    for command, name in commands:
        completed = subprocess.run(command, cwd=workspace, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"{name} failed: {(completed.stderr or completed.stdout).strip()}")
    return directory


def process_job(job: dict) -> None:
    workspace: Path | None = None

    try:
        if job["repository"] != settings.allowed_repository:
            raise RuntimeError(
                f"Nem engedélyezett repository: {job['repository']}"
            )

        workspace = checkout_exact_commit(job)
        app_dir = workspace / "apps" / "sample-app"

        if not app_dir.is_dir():
            raise RuntimeError(f"Nem található alkalmazásmappa: {app_dir}")

        evidence_directory = generate_security_evidence(workspace, job["commit_hash"])
        logger.info("Security evidence saved: %s", evidence_directory)

        logger.info("Dependency security scan indítása: job=%s", job["id"])
        audit_python_dependencies(app_dir)
        logger.info("Dependency security scan sikeres: job=%s", job["id"])

        result = build_and_deploy_app(
            app_name="sample-app",
            app_dir=str(app_dir),
            repo_url=job["repository"],
            internal_port=8000,
            commit_hash=job["commit_hash"],
            image_scan_report_path=report_path(job["commit_hash"], "image-scan"),
        )

        if result.get("status") != "success":
            raise RuntimeError(result.get("message", "A Docker deploy sikertelen."))

        container_id = result.get("container_id") if isinstance(result, dict) else None

        finish_deployment(
            job_id=job["id"],
            status="success",
            logs=("Dependency security gate passed. " f"Deploy sikeres. Commit: {job['commit_hash']}"),
            container_id=container_id,
        )
        logger.info("Deploy sikeres: job=%s", job["id"])

    except Exception as error:
        logger.exception("Deploy sikertelen: job=%s", job["id"])
        finish_deployment(
            job_id=job["id"],
            status="failed",
            logs=str(error),
            container_id=None,
        )

    finally:
        if workspace is not None:
            shutil.rmtree(workspace, ignore_errors=True)


def main() -> None:
    init_db()
    recovered = recover_interrupted_deployments()
    if recovered:
        logger.warning("%s félbeszakadt deployment újra sorba állítva.", recovered)
    logger.info("Deployment worker elindult.")

    while True:
        job = claim_next_deployment()

        if job is None:
            time.sleep(settings.poll_interval_seconds)
            continue

        process_job(job)


if __name__ == "__main__":
    main()
