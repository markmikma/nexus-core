import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from src.db import enqueue_deployment, init_db, record_webhook_event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.orchestrator")

WEBHOOK_SECRET = os.getenv("GITEA_WEBHOOK_SECRET", "")
ALLOWED_REPOSITORY = os.getenv("NEXUS_ALLOWED_REPOSITORY", "")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Nexus-Core Orchestrator", lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "nexus-orchestrator"}


@app.post("/webhooks/gitea")
async def receive_gitea_webhook(request: Request):
    if not WEBHOOK_SECRET or not ALLOWED_REPOSITORY:
        raise HTTPException(status_code=503, detail="Webhook policy is not configured.")

    payload = await request.body()
    signature = request.headers.get("X-Gitea-Signature", "")
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
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

    if repo != ALLOWED_REPOSITORY:
        logger.warning("Ignored push from non-allowed repository: %s", repo)
        return {"accepted": True, "action": "repository_not_allowed"}

    if not record_webhook_event(delivery_id, event, repo, ref, commit):
        return {"accepted": True, "action": "duplicate_ignored"}

    job_id = enqueue_deployment(
        delivery_id=delivery_id,
        app_name="sample-app",
        repository=repo,
        commit_hash=commit,
    )

    logger.info("Queued deployment job=%s repo=%s commit=%s", job_id, repo, commit)
    return {"accepted": True, "action": "queued", "job_id": job_id}