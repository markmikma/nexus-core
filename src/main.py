import hashlib
import hmac
import logging
import os
import re
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from prometheus_client import Counter, Histogram, make_asgi_app

from src.config import settings
from src.db import (
    enqueue_webhook_deployment,
    get_deployment_job,
    init_db,
    list_deployment_jobs,
    record_webhook_event,
)
from src.schemas import (
    DeploymentJobResponse,
    DeploymentListResponse,
    DeploymentTriggerRequest,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.orchestrator")

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Nexus-Core Orchestrator", lifespan=lifespan)

HTTP_REQUESTS = Counter(
    "nexus_http_requests_total",
    "HTTP requests handled by Nexus-Core services.",
    ("service", "method", "path", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "nexus_http_request_duration_seconds",
    "HTTP request duration handled by Nexus-Core services.",
    ("service", "method", "path"),
)


@app.middleware("http")
async def collect_http_metrics(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    started = time.perf_counter()
    response = await call_next(request)
    labels = ("orchestrator", request.method, request.url.path)
    HTTP_REQUESTS.labels(*labels, str(response.status_code)).inc()
    HTTP_REQUEST_DURATION.labels(*labels).observe(time.perf_counter() - started)
    return response


app.mount("/metrics", make_asgi_app())


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "nexus-orchestrator"}


def require_status_token(request: Request) -> None:
    if not settings.status_token:
        raise HTTPException(status_code=503, detail="Status API is not configured.")

    supplied_token = request.headers.get("X-Nexus-Status-Token", "")
    if not hmac.compare_digest(supplied_token, settings.status_token):
        raise HTTPException(status_code=401, detail="Invalid status token.")


def require_deploy_token(request: Request) -> None:
    if not settings.deploy_token:
        raise HTTPException(status_code=503, detail="Deployment API is not configured.")

    supplied_token = request.headers.get("X-Nexus-Deploy-Token", "")
    if not hmac.compare_digest(supplied_token, settings.deploy_token):
        raise HTTPException(status_code=401, detail="Invalid deployment token.")


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


@app.post("/deployments/trigger")
def trigger_verified_deployment(
    payload: DeploymentTriggerRequest,
    request: Request,
):
    """Queue a deployment only after a trusted CI workflow has succeeded."""
    require_deploy_token(request)

    if payload.repository != settings.allowed_repository:
        raise HTTPException(status_code=403, detail="Repository is not allowed.")
    if payload.ref != "refs/heads/main":
        raise HTTPException(status_code=400, detail="Only main deployments are allowed.")
    if not re.fullmatch(r"[0-9a-f]{40}", payload.commit_hash):
        raise HTTPException(status_code=400, detail="Invalid commit hash.")

    job_id = enqueue_webhook_deployment(
        delivery_id=payload.delivery_id,
        event_type="ci_success",
        app_name="sample-app",
        repository=payload.repository,
        ref=payload.ref,
        commit_hash=payload.commit_hash,
    )
    if job_id is None:
        return {"accepted": True, "action": "duplicate_ignored"}

    logger.info(
        "Queued verified deployment job=%s repo=%s commit=%s",
        job_id,
        payload.repository,
        payload.commit_hash,
    )
    return {"accepted": True, "action": "queued", "job_id": job_id}


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

    recorded = record_webhook_event(
        delivery_id=delivery_id,
        event_type=event,
        repository=repo,
        ref=ref,
        commit_hash=commit,
    )
    if not recorded:
        return {"accepted": True, "action": "duplicate_ignored"}

    logger.info("Push accepted for CI: repo=%s commit=%s", repo, commit)
    return {"accepted": True, "action": "ci_required"}
