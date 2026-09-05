import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from src.db import init_db, record_webhook_event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.orchestrator")

WEBHOOK_SECRET = os.getenv("GITEA_WEBHOOK_SECRET", "")


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
    if not WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook secret is not configured.")

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
    body = await request.json()

    repo = body.get("repository", {}).get("full_name", "unknown")
    ref = body.get("ref", "")
    commit = body.get("after", "")

    if event != "push" or ref != "refs/heads/main":
        return {"accepted": True, "action": "ignored"}

    is_new = record_webhook_event(delivery_id, event, repo, ref, commit)
    if not is_new:
        return {"accepted": True, "action": "duplicate_ignored"}

    logger.info("Accepted main push repo=%s commit=%s", repo, commit)
    return {"accepted": True, "action": "queued"}