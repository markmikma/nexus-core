import hashlib
import hmac
import logging
import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request

from src.config import settings
from src.db import (
    enqueue_webhook_deployment,
    get_deployment_job,
    init_db,
    list_deployment_jobs,
)
from src.schemas import DeploymentJobResponse, DeploymentListResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.orchestrator")

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Nexus-Core Orchestrator", lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "nexus-orchestrator"}


def require_status_token(request: Request) -> None:
    if not settings.status_token:
        raise HTTPException(status_code=503, detail="Status API is not configured.")

    supplied_token = request.headers.get("X-Nexus-Status-Token", "")
    if not hmac.compare_digest(supplied_token, settings.status_token):
        raise HTTPException(status_code=401, detail="Invalid status token.")


@app.get("/deployments", response_model=DeploymentListResponse)
def list_deployments(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
):
    require_status_token(request)
    jobs = list_deployment_jobs(limit=limit)
    return {"items": jobs, "count": len(jobs)}


@app.get("/deployments/{job_id}", response_model=DeploymentJobResponse)
def get_deployment(job_id: int, request: Request):
    require_status_token(request)
    job = get_deployment_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Deployment job not found.")
    return job


@app.post("/webhooks/gitea")
async def receive_gitea_webhook(request: Request):
    if not settings.webhook_secret or not settings.allowed_repository:
        raise HTTPException(status_code=503, detail="Webhook policy is not configured.")

    payload = await request.body()
    signature = request.headers.get("X-Gitea-Signature", "")
    expected = hmac.new(
        settings.webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")

    event = request.headers.get("X-Gitea-Event", "unknown")
    delivery_id = request.headers.get("X-Gitea-Delivery", "")
    if not delivery_id:
        raise HTTPException(status_code=400, detail="Missing Gitea delivery ID.")

    body = await request.json()
    repo = body.get("repository", {}).get("full_name", "unknown")
    ref = body.get("ref", "")
    commit = body.get("after", "")

    if event != "push" or ref != "refs/heads/main":
        return {"accepted": True, "action": "ignored"}

    if repo != settings.allowed_repository:
        logger.warning("Ignored push from non-allowed repository: %s", repo)
        return {"accepted": True, "action": "repository_not_allowed"}

    if not re.fullmatch(r"[0-9a-f]{40}", commit) or commit == "0" * 40:
        raise HTTPException(status_code=400, detail="Invalid push commit hash.")

    job_id = enqueue_webhook_deployment(
        delivery_id=delivery_id,
        event_type=event,
        app_name="sample-app",
        repository=repo,
        ref=ref,
        commit_hash=commit,
    )

    if job_id is None:
        return {"accepted": True, "action": "duplicate_ignored"}

    logger.info("Queued deployment job=%s repo=%s commit=%s", job_id, repo, commit)
    return {"accepted": True, "action": "queued", "job_id": job_id}
