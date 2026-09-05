import logging
import os
import time
from pathlib import Path

from src.db import claim_next_deployment, finish_deployment, init_db
from src.docker_engine import build_and_deploy_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.worker")

POLL_INTERVAL_SECONDS = 3
ALLOWED_REPOSITORY = os.getenv("NEXUS_ALLOWED_REPOSITORY", "")
APP_SOURCE_DIR = Path(
    os.getenv("NEXUS_SAMPLE_APP_DIR", "/workspace/apps/sample-app")
)
REPOSITORY_URL = "ssh://git@gitea.localhost:2223/nexusadmin/nexus-core.git"


def process_job(job: dict):
    job_id = job["id"]
    repository = job["repository"]

    if repository != ALLOWED_REPOSITORY:
        finish_deployment(job_id, "failed", "Repository policy rejected the job.")
        return

    if not APP_SOURCE_DIR.is_dir():
        finish_deployment(
            job_id,
            "failed",
            f"Sample app source not found: {APP_SOURCE_DIR}",
        )
        return

    logger.info(
        "Starting deployment job=%s app=%s commit=%s",
        job_id,
        job["app_name"],
        job["commit_hash"],
    )

    result = build_and_deploy_app(
        app_name="sample-app",
        app_dir=str(APP_SOURCE_DIR),
        repo_url=REPOSITORY_URL,
        internal_port=8000,
    )

    if result["status"] == "success":
        finish_deployment(
            job_id,
            "success",
            "Build and Traefik deployment completed.",
            result["container_id"],
        )
        logger.info("Deployment job=%s completed", job_id)
    else:
        finish_deployment(job_id, "failed", result["message"])
        logger.error("Deployment job=%s failed: %s", job_id, result["message"])


def main():
    init_db()
    logger.info("Nexus deployment worker started.")

    while True:
        job = claim_next_deployment()
        if job is None:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        try:
            process_job(job)
        except Exception as error:
            logger.exception("Unexpected worker error.")
            finish_deployment(job["id"], "failed", str(error))


if __name__ == "__main__":
    main()