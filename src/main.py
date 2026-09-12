import hashlib
import hmac
import logging
import os
import re
import time
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app

from src.auth import COOKIE_NAME, make_session, read_session, verify_password
from src.config import settings
from src.db import (
    enqueue_webhook_deployment,
    enqueue_deployment,
    get_deployment_job,
    latest_successful_deployment,
    queued_deployment_count,
    init_db,
    list_deployment_jobs,
    list_security_events,
    log_security_event,
    record_webhook_event,
)
from src.reporting import list_reports, report_path
from src.release import can_promote
from src.schemas import (
    DeploymentJobResponse,
    DeploymentListResponse,
    DeploymentTriggerRequest,
    PromotionRequest,
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
DEPLOYMENT_QUEUE_DEPTH = Gauge(
    "nexus_deployment_queue_depth",
    "Number of deployment jobs waiting for a worker.",
)

SECURITY_EVENTS = Counter(
    "nexus_security_events_total",
    "Security-relevant Nexus events.",
    ("event_type", "outcome", "actor"),
)


def audit_security_event(event_type: str, outcome: str, actor: str, detail: str | None = None) -> None:
    SECURITY_EVENTS.labels(event_type, outcome, actor).inc()
    log_security_event(event_type, outcome, actor, detail)


@app.middleware("http")
async def collect_http_metrics(request: Request, call_next):
    if request.url.path == "/metrics":
        DEPLOYMENT_QUEUE_DEPTH.set(queued_deployment_count())
        return await call_next(request)

    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'"
    labels = ("orchestrator", request.method, request.url.path)
    HTTP_REQUESTS.labels(*labels, str(response.status_code)).inc()
    HTTP_REQUEST_DURATION.labels(*labels).observe(time.perf_counter() - started)
    return response


app.mount("/metrics", make_asgi_app())


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(Path(__file__).with_name("dashboard.html"), media_type="text/html")


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "nexus-orchestrator"}


@app.get("/readyz")
def readyz():
    missing = []
    if not settings.status_token:
        missing.append("status_token")
    if not settings.session_secret:
        missing.append("session_secret")
    try:
        queued = queued_deployment_count()
    except Exception as error:
        raise HTTPException(status_code=503, detail="Database is not ready.") from error
    if missing:
        raise HTTPException(status_code=503, detail={"missing_configuration": missing})
    return {"status": "ready", "queued_deployments": queued}


def require_status_token(request: Request) -> str:
    """Authorize a signed local session or automation status token."""
    supplied_token = request.headers.get("X-Nexus-Status-Token", "")
    if settings.status_token and hmac.compare_digest(supplied_token, settings.status_token):
        audit_security_event("status_api_access", "success", "automation-token", request.url.path)
        return "admin"

    session_role = read_session(request.cookies.get(COOKIE_NAME), settings.session_secret)
    if session_role:
        audit_security_event("dashboard_session", "success", session_role, request.url.path)
        return session_role

    audit_security_event("dashboard_session", "failure", "unknown", request.url.path)
    raise HTTPException(status_code=401, detail="Valid dashboard session or status token required.")


def require_deploy_token(request: Request) -> None:
    if not settings.deploy_token:
        raise HTTPException(status_code=503, detail="Deployment API is not configured.")

    supplied_token = request.headers.get("X-Nexus-Deploy-Token", "")
    if not hmac.compare_digest(supplied_token, settings.deploy_token):
        raise HTTPException(status_code=401, detail="Invalid deployment token.")


@app.post("/auth/login")
async def login(request: Request):
    if not settings.session_secret:
        raise HTTPException(status_code=503, detail="Dashboard session signing is not configured.")
    body = await request.json()
    username, password = body.get("username", ""), body.get("password", "")
    role = "admin" if username == "admin" and verify_password(password, settings.dashboard_admin_hash) else "viewer" if username == "viewer" and verify_password(password, settings.dashboard_viewer_hash) else None
    if not role:
        audit_security_event("dashboard_login", "failure", username or "unknown", "/auth/login")
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    response = JSONResponse({"role": role})
    response.set_cookie(COOKIE_NAME, make_session(role, settings.session_secret), httponly=True, secure=settings.dashboard_cookie_secure, samesite="strict", max_age=28800)
    audit_security_event("dashboard_login", "success", username, "/auth/login")
    return response


@app.post("/auth/logout")
def logout(request: Request):
    role = read_session(request.cookies.get(COOKIE_NAME), settings.session_secret)
    response = JSONResponse({"logged_out": True})
    response.delete_cookie(COOKIE_NAME, httponly=True, secure=settings.dashboard_cookie_secure, samesite="strict")
    audit_security_event("dashboard_logout", "success", role or "unknown", "/auth/logout")
    return response


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


@app.get("/security-reports/{commit_hash}")
def get_security_reports(commit_hash: str, request: Request):
    role = require_status_token(request)
    if role != "admin": raise HTTPException(status_code=403, detail="Admin role required.")
    try:
        return {"commit_hash": commit_hash, "items": list_reports(commit_hash)}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/security-reports/{commit_hash}/{report_type}")
def download_security_report(commit_hash: str, report_type: str, request: Request):
    role = require_status_token(request)
    if role != "admin": raise HTTPException(status_code=403, detail="Admin role required.")
    try:
        path = report_path(commit_hash, report_type)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Security report not found.")
    return FileResponse(path, media_type="application/json", filename=path.name)


@app.get("/security-events")
def get_security_events(request: Request, limit: int = Query(default=50, ge=1, le=200)):
    role = require_status_token(request)
    if role != "admin": raise HTTPException(status_code=403, detail="Admin role required.")
    events = list_security_events(limit)
    return {"items": events, "count": len(events)}


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
        environment=payload.environment,
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


@app.post("/releases/promote")
def promote_release(payload: PromotionRequest, request: Request):
    role = require_status_token(request)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required.")
    if not can_promote(payload.source_environment, payload.target_environment):
        raise HTTPException(
            status_code=400,
            detail="Only dev to staging and staging to production promotions are allowed.",
        )

    source = latest_successful_deployment(payload.source_environment)
    if source is None:
        raise HTTPException(status_code=404, detail="No successful source release is available.")

    delivery_id = (
        f"promotion-{payload.source_environment}-to-{payload.target_environment}-"
        f"{source['commit_hash']}"
    )
    job_id = enqueue_deployment(
        delivery_id=delivery_id,
        app_name="sample-app",
        repository=source["repository"],
        commit_hash=source["commit_hash"],
        environment=payload.target_environment,
    )
    audit_security_event(
        "release_promotion",
        "success",
        "admin",
        f"{payload.source_environment}->{payload.target_environment}:{source['commit_hash']}",
    )
    return {
        "accepted": True,
        "source_environment": payload.source_environment,
        "target_environment": payload.target_environment,
        "commit_hash": source["commit_hash"],
        "job_id": job_id,
        "action": "queued" if job_id else "duplicate_ignored",
    }


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
